import pygame
import subprocess
import threading
import os
import time
import textwrap
import math
import pyautogui  # Requires: pip install pyautogui
import datetime  # For formatting log timestamps
import csv  # For CSV logging

# -------------------------------
# Initialize Full-Screen & Get Screen Size
# -------------------------------
pygame.init()
info = pygame.display.Info()
SCREEN_WIDTH, SCREEN_HEIGHT = info.current_w, info.current_h
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Xbox 360 RPCS3 Launcher")

# -------------------------------
# Colors & Fonts (Xbox 360 Themed)
# -------------------------------
BACKGROUND_COLOR = (30, 30, 30)  # Dark background
HEADER_COLOR = (20, 20, 20)  # Dark header area
TEXT_COLOR = (255, 255, 255)  # White text
HIGHLIGHT_COLOR = (16, 124, 16)  # Xbox green for selection highlight
SLOT_BG_COLOR = (40, 40, 40)  # Slot background for game containers
TEXT_BOX_COLOR = (50, 50, 50)  # Background for text container

# -------------------------------
# UI Layout Constants (Relative to Screen Size)
# -------------------------------
HEADER_HEIGHT = int(SCREEN_HEIGHT * 0.1)  # 10% of screen height
outer_padding_x = int(SCREEN_WIDTH * 0.05)  # 5% horizontal padding
outer_padding_y = int(SCREEN_HEIGHT * 0.05)  # 5% vertical padding
inner_margin_x = int(SCREEN_WIDTH * 0.02)  # 2% gap between grid items horizontally
inner_margin_y = int(SCREEN_HEIGHT * 0.02)  # 2% gap between grid items vertically
columns = 4  # Fixed: 4 games per row

SWITCH_DELAY_MS = 300  # Minimum delay between navigation moves

# -------------------------------
# Paths & Global Variables
# -------------------------------
CWD = os.path.dirname(os.path.realpath(__file__))
RPCS3_PATH = os.path.join(CWD, "RPCS3")
GAMES = []  # Populated by retrieve_games()
grid_scroll_y = 0  # Vertical scroll offset for grid
game_loaded = False  # Set to True when the game is first loaded

# Global variable for the controller (joystick)
joystick = None

# New global variables for the shutdown menu
menu_active = False
pause_button_last_state = False  # Used to debounce the pause button

# Global variables for screen time logging
current_game_title = None
game_start_time = None

# CSV log file path
log_file = "screen_time_log.csv"


# -------------------------------
# Helper Functions
# -------------------------------
def scale_image_preserve_aspect(image, max_width, max_height):
    width, height = image.get_size()
    scale = min(max_width / width, max_height / height)
    new_size = (int(width * scale), int(height * scale))
    return pygame.transform.scale(image, new_size)


def render_text_wrapped(text, font, color, max_width):
    avg_char_width = font.size("A")[0]
    max_chars = max_width // avg_char_width if avg_char_width else max_width
    wrapped_lines = textwrap.wrap(text, width=max_chars)
    line_surfaces = [font.render(line, True, color) for line in wrapped_lines]
    width = max((surface.get_width() for surface in line_surfaces), default=max_width)
    height = sum(surface.get_height() for surface in line_surfaces)
    text_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for surface in line_surfaces:
        text_surface.blit(surface, (0, y))
        y += surface.get_height()
    return text_surface


# -------------------------------
# Controller Hot-Plugging Support
# -------------------------------
def check_for_new_controller():
    """Checks periodically if a controller is connected, and if so, initializes it."""
    global joystick
    if pygame.joystick.get_count() > 0:
        if joystick is None or not joystick.get_init():
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            print(f"Controller connected: {joystick.get_name()}")
    else:
        # If a controller was previously connected but now is disconnected.
        if joystick is not None:
            print("Controller disconnected.")
            joystick.quit()
            joystick = None


# -------------------------------
# Shutdown Function
# -------------------------------
def shutdown_system():
    """Immediately shuts down the Windows computer."""
    print("Shutting down system in 5 seconds...")
    subprocess.run(["shutdown", "/s", "/t", "5"], shell=False)
    # For hibernate, use: subprocess.run(["shutdown", "/h"], shell=False)


# -------------------------------
# Draw Shutdown Menu Overlay
# -------------------------------
def draw_shutdown_menu():
    """Draw a semi-transparent overlay with the shutdown menu."""
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    overlay.set_alpha(180)
    overlay.fill((0, 0, 0))
    screen.blit(overlay, (0, 0))

    menu_width = int(SCREEN_WIDTH * 0.5)
    menu_height = int(SCREEN_HEIGHT * 0.3)
    menu_x = (SCREEN_WIDTH - menu_width) // 2
    menu_y = (SCREEN_HEIGHT - menu_height) // 2
    menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
    pygame.draw.rect(screen, HEADER_COLOR, menu_rect, border_radius=10)

    menu_text = HEADER_FONT.render("Shutdown", True, HIGHLIGHT_COLOR)
    text_x = menu_x + (menu_width - menu_text.get_width()) // 2
    text_y = menu_y + int(menu_height * 0.3) - menu_text.get_height() // 2
    screen.blit(menu_text, (text_x, text_y))

    instruction_text = FONT.render("Press A to shutdown, Pause to cancel", True, TEXT_COLOR)
    inst_x = menu_x + (menu_width - instruction_text.get_width()) // 2
    inst_y = menu_y + int(menu_height * 0.7) - instruction_text.get_height() // 2
    screen.blit(instruction_text, (inst_x, inst_y))


# -------------------------------
# PlaystationGame Class
# -------------------------------
class PlaystationGame:
    def __init__(self, title, gamepath, runpath, console='PS3', image=None, icon=None):
        self.title = title
        self.gamepath = gamepath
        self.runpath = runpath
        self.console = console
        self.image = image  # PIC1 image
        self.icon = icon  # ICON0 image

    def __str__(self):
        return self.title

    def play(self):
        global current_game_title, game_start_time
        # Record the start time and game name for logging.
        current_game_title = self.title
        game_start_time = time.time()
        # Start the monitor in a separate thread before launching the game.
        t = threading.Thread(target=monitor, args=())
        t.start()
        self.start_game()

    def start_game(self):
        program = os.path.join(RPCS3_PATH, "rpcs3.exe")
        subprocess.Popen([program, self.runpath], shell=False)
        print(f"Launching: {self.title}")


# -------------------------------
# Monitor Function with ALT+ENTER, ALT+TAB, and CSV Logging
# -------------------------------
def monitor():
    """Monitors RPCS3 and:
       - When first loaded (kb_ram > 1,000,000 and game_loaded is False), sends ALT+ENTER
         to trigger fullscreen for RPCS3 and minimizes (iconifies) the dashboard.
       - When the game is closed (kb_ram < 700,000), kills RPCS3, logs play time, and simulates ALT+TAB.
    """
    global game_loaded, game_start_time, current_game_title
    print("Monitoring RPCS3...")
    time.sleep(3)

    while True:
        process = subprocess.run("tasklist | findstr rpcs3", shell=True, capture_output=True, text=True)
        output = process.stdout.strip()
        if not output:
            print("RPCS3 not found.")
            time.sleep(1)
            if game_loaded:
                # Record end time and compute elapsed duration.
                game_end_time = time.time()
                start_str = datetime.datetime.fromtimestamp(game_start_time).strftime("%Y-%m-%d %H:%M:%S")
                end_str = datetime.datetime.fromtimestamp(game_end_time).strftime("%Y-%m-%d %H:%M:%S")
                duration_seconds = int(game_end_time - game_start_time)
                duration_str = str(datetime.timedelta(seconds=duration_seconds))
                # Write log to CSV.
                # If the file doesn't exist, write the header first.
                if not os.path.exists(log_file):
                    with open(log_file, "w", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Game", "Start", "End", "Time Played"])
                with open(log_file, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([current_game_title, start_str, end_str, duration_str])
                print(f"Logged play time for {current_game_title}.")
                game_loaded = False
                pyautogui.hotkey('alt', 'tab')
                break
            continue
        stdout = [x for x in process.stdout.split(" ") if x != '']
        if len(stdout) < 3:
            time.sleep(1)
            continue
        psid = stdout[1]
        try:
            kb_ram = int(stdout[-2].replace(",", ""))
        except ValueError:
            kb_ram = 0
        print(f"RPCS3 RAM Usage: {kb_ram} KB")
        time.sleep(1)
        # When game first loads, send ALT+ENTER and minimize dashboard.
        if not game_loaded and kb_ram > 1_000_000:
            game_loaded = True
            pyautogui.hotkey('alt', 'enter')
            print("Sent ALT+ENTER to toggle fullscreen for RPCS3.")
            pygame.display.iconify()  # Minimize the dashboard
        # When game is closed, kill RPCS3, log screen time, and bring dashboard to front.
        if game_loaded and kb_ram < 700_000:
            print(f"Game exited, stopping RPCS3 (PID {psid}).")
            subprocess.run(f"taskkill /PID {psid} /F", shell=False)
            # Record end time and compute elapsed duration.
            game_end_time = time.time()
            start_str = datetime.datetime.fromtimestamp(game_start_time).strftime("%Y-%m-%d %H:%M:%S")
            end_str = datetime.datetime.fromtimestamp(game_end_time).strftime("%Y-%m-%d %H:%M:%S")
            duration_seconds = int(game_end_time - game_start_time)
            duration_str = str(datetime.timedelta(seconds=duration_seconds))
            # Write log to CSV.
            # If the file doesn't exist, write the header first.
            if not os.path.exists(log_file):
                with open(log_file, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Game", "Start", "End", "Time Played"])
            with open(log_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([current_game_title, start_str, end_str, duration_str])
            print(f"Logged play time for {current_game_title}.")
            game_loaded = False
            pyautogui.hotkey('alt', 'tab')
            break


# -------------------------------
# Game Retrieval & Image Loading
# -------------------------------
def retrieve_games():
    """Scans the ./PS3 directory for games and returns a list of PlaystationGame objects."""
    directory_path = "./PS3"
    games = []
    if not os.path.exists(directory_path):
        print("PS3 directory not found.")
        return games

    game_directories = [d for d in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, d))]
    for game_dir in game_directories:
        title_path = os.path.join(directory_path, game_dir, "Title.txt")
        if os.path.exists(title_path):
            with open(title_path, "r") as f:
                title = f.read().strip()
            runpath = os.path.join(directory_path, game_dir, "PS3_GAME", "USRDIR", "EBOOT.BIN")
            # Load main game image (PIC1.PNG)
            image_path = os.path.join(directory_path, game_dir, "PS3_GAME", "PIC1.PNG")
            if os.path.exists(image_path):
                try:
                    image = pygame.image.load(image_path).convert_alpha()
                except Exception as e:
                    print(f"Error loading PIC1 for {title}: {e}")
                    image = None
            else:
                image = None
            # Load icon image (ICON0.PNG)
            icon_path = os.path.join(directory_path, game_dir, "PS3_GAME", "ICON0.PNG")
            if os.path.exists(icon_path):
                try:
                    icon = pygame.image.load(icon_path).convert_alpha()
                except Exception as e:
                    print(f"Error loading ICON0 for {title}: {e}")
                    icon = None
            else:
                icon = None
            games.append(
                PlaystationGame(title, os.path.join(directory_path, game_dir), runpath, image=image, icon=icon))
    return games


# -------------------------------
# UI Fonts Setup
# -------------------------------
FONT = pygame.font.Font(None, 32)
HEADER_FONT = pygame.font.Font(None, 64)
FOOTER_FONT = pygame.font.Font(None, 28)

# Load games
GAMES = retrieve_games()
if not GAMES:
    print("No games found. Exiting.")
    pygame.quit()
    exit()

selected_index = 0
last_switch_time = 0  # For navigation debounce


# -------------------------------
# Grid Navigation Helpers
# -------------------------------
def update_grid_scroll(total_grid_height, grid_item_height, rows):
    """Ensure the selected game is visible in the grid vertically."""
    global grid_scroll_y
    viewport_height = SCREEN_HEIGHT - HEADER_HEIGHT
    selected_row = selected_index // columns
    item_y = outer_padding_y + selected_row * (grid_item_height + inner_margin_y)
    item_bottom = item_y + grid_item_height
    if item_y - grid_scroll_y < 0:
        grid_scroll_y = item_y
    elif item_bottom - grid_scroll_y > viewport_height:
        grid_scroll_y = item_bottom - viewport_height
    max_scroll = max(0, total_grid_height - viewport_height)
    grid_scroll_y = max(0, min(grid_scroll_y, max_scroll))


def get_grid_dimensions():
    """Compute grid item dimensions based on screen size and number of rows."""
    total_games = len(GAMES)
    rows = math.ceil(total_games / columns)
    available_width = SCREEN_WIDTH - 2 * outer_padding_x - (columns - 1) * inner_margin_x
    grid_item_width = available_width / columns
    available_height = SCREEN_HEIGHT - HEADER_HEIGHT - 2 * outer_padding_y - (rows - 1) * inner_margin_y
    grid_item_height = available_height / rows if rows > 0 else 0
    total_grid_height = 2 * outer_padding_y + rows * grid_item_height + (rows - 1) * inner_margin_y
    return grid_item_width, grid_item_height, rows, total_grid_height


# -------------------------------
# Draw UI Function (Including Footer Instructions)
# -------------------------------
def draw_ui():
    """Render the grid-based game selection UI with Xbox 360 theming and footer instructions."""
    screen.fill(BACKGROUND_COLOR)

    # Draw header area
    header_rect = pygame.Rect(0, 0, SCREEN_WIDTH, HEADER_HEIGHT)
    pygame.draw.rect(screen, HEADER_COLOR, header_rect)
    header_text = HEADER_FONT.render("XBOX 360 DASHBOARD", True, HIGHLIGHT_COLOR)
    screen.blit(header_text, (SCREEN_WIDTH // 2 - header_text.get_width() // 2,
                              HEADER_HEIGHT // 2 - header_text.get_height() // 2))

    grid_item_width, grid_item_height, rows, total_grid_height = get_grid_dimensions()

    # Draw each game slot in the grid
    for i, game in enumerate(GAMES):
        row = i // columns
        col = i % columns
        x = outer_padding_x + col * (grid_item_width + inner_margin_x)
        y = HEADER_HEIGHT + outer_padding_y + row * (grid_item_height + inner_margin_y) - grid_scroll_y

        slot_rect = pygame.Rect(x, y, grid_item_width, grid_item_height)
        pygame.draw.rect(screen, SLOT_BG_COLOR, slot_rect, border_radius=10)

        cover_area_height = grid_item_height * 0.70
        text_area_height = grid_item_height - cover_area_height

        # Draw cover image (PIC1)
        if game.image:
            cover_image = scale_image_preserve_aspect(game.image, grid_item_width, cover_area_height)
            cover_rect = cover_image.get_rect()
            cover_rect.center = (x + grid_item_width / 2, y + cover_area_height / 2)
            screen.blit(cover_image, cover_rect.topleft)
        else:
            pygame.draw.rect(screen, TEXT_COLOR, (x, y, grid_item_width, cover_area_height), 2)

        # Draw ICON0 at top-left within cover area
        if game.icon:
            icon_image = scale_image_preserve_aspect(game.icon, grid_item_width * 0.3, cover_area_height * 0.3)
            screen.blit(icon_image, (x + 10, y + 10))

        # Draw text container for game title
        text_padding = 5
        text_container_width = grid_item_width - 2 * text_padding
        title_surface = render_text_wrapped(game.title, FONT, TEXT_COLOR, text_container_width)
        text_box_width = title_surface.get_width() + 2 * text_padding
        text_box_height = title_surface.get_height() + 2 * text_padding
        text_box_x = x + (grid_item_width - text_box_width) / 2
        text_box_y = y + cover_area_height + (text_area_height - text_box_height) / 2
        text_box_rect = pygame.Rect(text_box_x, text_box_y, text_box_width, text_box_height)
        pygame.draw.rect(screen, TEXT_BOX_COLOR, text_box_rect, border_radius=5)
        screen.blit(title_surface, (text_box_x + text_padding, text_box_y + text_padding))

        # Highlight the selected slot
        if i == selected_index:
            pygame.draw.rect(screen, HIGHLIGHT_COLOR, slot_rect, 4, border_radius=10)

    # Draw footer instructions at the bottom (updated to remove "B to quit")
    footer_text = FOOTER_FONT.render("Press A to select game, Pause for menu", True, TEXT_COLOR)
    footer_y = SCREEN_HEIGHT - outer_padding_y - footer_text.get_height()
    screen.blit(footer_text, (SCREEN_WIDTH // 2 - footer_text.get_width() // 2, footer_y))


# -------------------------------
# Main Loop
# -------------------------------
running = True
clock = pygame.time.Clock()

while running:
    current_time = pygame.time.get_ticks()

    # Check for controller connection (hot-plug support)
    check_for_new_controller()

    # Process events (keyboard for debugging/exit)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        # Allow quitting via the ESC key
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            # Keyboard navigation (arrow keys) only if menu is not active
            if not menu_active and current_time - last_switch_time > SWITCH_DELAY_MS:
                if event.key == pygame.K_LEFT and selected_index % columns > 0:
                    selected_index -= 1
                    last_switch_time = current_time
                elif event.key == pygame.K_RIGHT and (selected_index % columns) < (
                        columns - 1) and selected_index < len(GAMES) - 1:
                    selected_index += 1
                    last_switch_time = current_time
                elif event.key == pygame.K_UP and selected_index - columns >= 0:
                    selected_index -= columns
                    last_switch_time = current_time
                elif event.key == pygame.K_DOWN and selected_index + columns < len(GAMES):
                    selected_index += columns
                    last_switch_time = current_time

    # Process controller input
    if joystick:
        pygame.event.pump()

        # Always check for the pause button (assumed index 7) to toggle the shutdown menu.
        pause_button_state = joystick.get_button(7)
        if pause_button_state and not pause_button_last_state:
            menu_active = not menu_active
            last_switch_time = current_time
        pause_button_last_state = pause_button_state

        if menu_active:
            # When the menu is active, listen for A button to confirm shutdown.
            if joystick.get_button(0):
                shutdown_system()
        else:
            # Normal dashboard navigation only when the shutdown menu is not active.
            axis_x = joystick.get_axis(0)
            axis_y = joystick.get_axis(1)
            if current_time - last_switch_time > SWITCH_DELAY_MS:
                if axis_x < -0.5 and selected_index % columns > 0:
                    selected_index -= 1
                    last_switch_time = current_time
                elif axis_x > 0.5 and (selected_index % columns) < (columns - 1) and selected_index < len(GAMES) - 1:
                    selected_index += 1
                    last_switch_time = current_time
                if axis_y < -0.5 and selected_index - columns >= 0:
                    selected_index -= columns
                    last_switch_time = current_time
                elif axis_y > 0.5 and selected_index + columns < len(GAMES):
                    selected_index += columns
                    last_switch_time = current_time
            # Launch game if 'A' button (button 0) is pressed and menu is not active
            if joystick.get_button(0):
                GAMES[selected_index].play()
                pygame.time.wait(500)

    # Update grid scrolling and draw the UI
    _, grid_item_height, rows, total_grid_height = get_grid_dimensions()
    update_grid_scroll(total_grid_height, grid_item_height, rows)
    draw_ui()
    if menu_active:
        draw_shutdown_menu()
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
