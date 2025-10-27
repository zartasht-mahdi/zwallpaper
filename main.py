import customtkinter as ctk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import os
import threading
from pathlib import Path
import subprocess
import platform
import json

# Configuration
ARCHIVE_ITEM = "zwallpaper"  # CHANGE THIS to your Archive.org item identifier
ARCHIVE_BASE_URL = f"https://archive.org/download/{ARCHIVE_ITEM}/"

# App directories
HOME_DIR = Path.home()
APP_DIR = HOME_DIR / ".zwallpaper"
CACHE_DIR = APP_DIR / "cache"
THUMBNAILS_DIR = CACHE_DIR / "thumbnails"
WALLPAPERS_DIR = CACHE_DIR / "wallpapers"

# Create directories
APP_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
THUMBNAILS_DIR.mkdir(exist_ok=True)
WALLPAPERS_DIR.mkdir(exist_ok=True)


class WallpaperManager:
    """Handles wallpaper setting for different platforms"""
    
    @staticmethod
    def set_wallpaper(image_path):
        """Set wallpaper based on the operating system"""
        system = platform.system()
        
        try:
            if system == "Windows":
                import ctypes
                ctypes.windll.user32.SystemParametersInfoW(20, 0, str(image_path), 3)
                return True
            
            elif system == "Darwin":  # macOS
                script = f'''
                tell application "Finder"
                    set desktop picture to POSIX file "{image_path}"
                end tell
                '''
                subprocess.run(["osascript", "-e", script], check=True)
                return True
            
            elif system == "Linux":
                desktop = os.environ.get("DESKTOP_SESSION", "").lower()
                
                if "gnome" in desktop or "ubuntu" in desktop:
                    subprocess.run([
                        "gsettings", "set", "org.gnome.desktop.background",
                        "picture-uri", f"file://{image_path}"
                    ], check=True)
                elif "kde" in desktop or "plasma" in desktop:
                    subprocess.run([
                        "qdbus", "org.kde.plasmashell", "/PlasmaShell",
                        "org.kde.PlasmaShell.evaluateScript",
                        f'var allDesktops = desktops();for (i=0;i<allDesktops.length;i++) {{d = allDesktops[i];d.wallpaperPlugin = "org.kde.image";d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");d.writeConfig("Image", "file://{image_path}")}}'
                    ], check=True)
                elif "xfce" in desktop:
                    subprocess.run([
                        "xfconf-query", "-c", "xfce4-desktop",
                        "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                        "-s", str(image_path)
                    ], check=True)
                else:
                    subprocess.run(["feh", "--bg-scale", str(image_path)], check=True)
                return True
        
        except Exception as e:
            print(f"Error setting wallpaper: {e}")
            return False
        
        return False


class PreviewWindow(ctk.CTkToplevel):
    """Full-size preview window"""
    
    def __init__(self, parent, wallpaper_data, on_apply_callback, on_download_callback):
        super().__init__(parent)
        
        self.wallpaper_data = wallpaper_data
        self.on_apply_callback = on_apply_callback
        self.on_download_callback = on_download_callback
        self.full_image = None
        
        # Window setup
        self.title(f"Preview - {self.format_name(wallpaper_data['name'])}")
        self.geometry("1000x700")
        
        # Make it modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.winfo_screenheight() // 2) - (700 // 2)
        self.geometry(f"1000x700+{x}+{y}")
        
        self.create_ui()
        self.load_image()
    
    def format_name(self, filename):
        """Format filename to readable name"""
        name = filename.rsplit('.', 1)[0]
        for res in ['_4k', '_2k', '_1080p', '_1440p', '_2160p', '_8k']:
            name = name.replace(res, '')
        name = name.replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def create_ui(self):
        """Create preview UI"""
        # Main container
        main_frame = ctk.CTkFrame(self, fg_color="#0d0d0d")
        main_frame.pack(fill="both", expand=True)
        
        # Top bar with title
        top_bar = ctk.CTkFrame(main_frame, height=60, fg_color="#1a1a1a")
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        
        title = ctk.CTkLabel(
            top_bar,
            text=self.format_name(self.wallpaper_data['name']),
            font=("Arial", 18, "bold")
        )
        title.pack(side="left", padx=20, pady=15)
        
        # Close button
        close_btn = ctk.CTkButton(
            top_bar,
            text="✕",
            width=40,
            height=40,
            command=self.destroy,
            fg_color="transparent",
            hover_color="#3d3d3d"
        )
        close_btn.pack(side="right", padx=10, pady=10)
        
        # Image container (scrollable for large images)
        self.image_frame = ctk.CTkScrollableFrame(
            main_frame,
            fg_color="#000000"
        )
        self.image_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Loading label
        self.image_label = ctk.CTkLabel(
            self.image_frame,
            text="Loading preview...",
            font=("Arial", 16)
        )
        self.image_label.pack(expand=True, pady=50)
        
        # Bottom bar with actions
        bottom_bar = ctk.CTkFrame(main_frame, height=70, fg_color="#1a1a1a")
        bottom_bar.pack(fill="x")
        bottom_bar.pack_propagate(False)
        
        # Buttons container
        btn_container = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        btn_container.pack(expand=True)
        
        # Apply button
        self.apply_btn = ctk.CTkButton(
            btn_container,
            text="🖼️ Apply as Wallpaper",
            width=200,
            height=40,
            font=("Arial", 14, "bold"),
            command=self.apply_wallpaper,
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        self.apply_btn.pack(side="left", padx=10)
        
        # Download button
        self.download_btn = ctk.CTkButton(
            btn_container,
            text="💾 Download",
            width=200,
            height=40,
            font=("Arial", 14, "bold"),
            command=self.download_wallpaper,
            fg_color="#2d7a2d",
            hover_color="#1d5a1d"
        )
        self.download_btn.pack(side="left", padx=10)
        
        # Info label
        category = self.wallpaper_data.get('category', 'Unknown')
        self.info_label = ctk.CTkLabel(
            bottom_bar,
            text=f"Category: {category.title()}",
            font=("Arial", 11)
        )
        self.info_label.pack(side="bottom", pady=5)
    
    def load_image(self):
        """Load full resolution image for preview"""
        threading.Thread(target=self._load_image_worker, daemon=True).start()
    
    def _load_image_worker(self):
        """Worker thread for loading image"""
        try:
            wallpaper_path = WALLPAPERS_DIR / self.wallpaper_data['name']
            
            # Check cache first
            if wallpaper_path.exists():
                image = Image.open(wallpaper_path)
            else:
                # Download image
                response = requests.get(self.wallpaper_data['download_url'], timeout=30)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content))
            
            # Store original for applying
            self.full_image = image
            
            # Calculate size to fit in preview (max 960x600)
            max_width = 960
            max_height = 600
            
            img_width, img_height = image.size
            ratio = min(max_width / img_width, max_height / img_height)
            
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            preview_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to CTkImage
            ctk_image = ctk.CTkImage(
                light_image=preview_image,
                dark_image=preview_image,
                size=(new_width, new_height)
            )
            
            # Update UI
            self.after(0, lambda: self.display_image(ctk_image, img_width, img_height))
            
        except Exception as e:
            print(f"Error loading preview: {e}")
            self.after(0, lambda: self.image_label.configure(text=f"Failed to load preview\n{str(e)}"))
    
    def display_image(self, ctk_image, orig_width, orig_height):
        """Display the image in UI"""
        self.image_label.configure(
            image=ctk_image,
            text=""
        )
        
        # Update info with resolution
        category = self.wallpaper_data.get('category', 'Unknown')
        self.info_label.configure(
            text=f"Category: {category.title()} | Resolution: {orig_width}x{orig_height}px"
        )
    
    def apply_wallpaper(self):
        """Apply wallpaper"""
        self.apply_btn.configure(state="disabled", text="Applying...")
        threading.Thread(target=self._apply_worker, daemon=True).start()
    
    def _apply_worker(self):
        """Worker thread for applying wallpaper"""
        try:
            wallpaper_path = WALLPAPERS_DIR / self.wallpaper_data['name']
            
            # Save if not cached
            if not wallpaper_path.exists() and self.full_image:
                self.full_image.save(wallpaper_path, quality=95)
            elif not wallpaper_path.exists():
                # Download if we don't have it
                response = requests.get(self.wallpaper_data['download_url'], timeout=30)
                response.raise_for_status()
                with open(wallpaper_path, 'wb') as f:
                    f.write(response.content)
            
            # Apply wallpaper
            success = WallpaperManager.set_wallpaper(wallpaper_path)
            
            if success:
                self.after(0, lambda: self.apply_btn.configure(
                    state="normal",
                    text="✓ Applied Successfully!"
                ))
                if self.on_apply_callback:
                    self.on_apply_callback(self.wallpaper_data['name'])
            else:
                self.after(0, lambda: self.apply_btn.configure(
                    state="normal",
                    text="❌ Failed to Apply"
                ))
        
        except Exception as e:
            print(f"Error applying wallpaper: {e}")
            self.after(0, lambda: self.apply_btn.configure(
                state="normal",
                text="❌ Failed"
            ))
    
    def download_wallpaper(self):
        """Download wallpaper to Downloads folder"""
        self.download_btn.configure(state="disabled", text="Downloading...")
        threading.Thread(target=self._download_worker, daemon=True).start()
    
    def _download_worker(self):
        """Worker thread for downloading"""
        try:
            # Get Downloads folder
            downloads_folder = Path.home() / "Downloads"
            downloads_folder.mkdir(exist_ok=True)
            
            download_path = downloads_folder / self.wallpaper_data['name']
            
            # Save image
            if self.full_image:
                self.full_image.save(download_path, quality=95)
            else:
                response = requests.get(self.wallpaper_data['download_url'], timeout=30)
                response.raise_for_status()
                with open(download_path, 'wb') as f:
                    f.write(response.content)
            
            self.after(0, lambda: self.download_btn.configure(
                state="normal",
                text="✓ Downloaded to Downloads!"
            ))
            
            if self.on_download_callback:
                self.on_download_callback(str(download_path))
        
        except Exception as e:
            print(f"Error downloading: {e}")
            self.after(0, lambda: self.download_btn.configure(
                state="normal",
                text="❌ Download Failed"
            ))


class WallpaperCard(ctk.CTkFrame):
    """Individual wallpaper card widget"""
    
    def __init__(self, parent, wallpaper_data, on_preview_callback):
        super().__init__(parent, fg_color="transparent")
        
        self.wallpaper_data = wallpaper_data
        self.on_preview_callback = on_preview_callback
        self.thumbnail_image = None
        
        # Card frame with hover effect
        self.card = ctk.CTkFrame(self, corner_radius=10, fg_color="#2b2b2b")
        self.card.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Make card clickable
        self.card.bind("<Button-1>", lambda e: self.show_preview())
        
        # Image placeholder
        self.image_label = ctk.CTkLabel(
            self.card, 
            text="Loading...",
            width=250,
            height=140,
            fg_color="#1a1a1a",
            corner_radius=8,
            cursor="hand2"
        )
        self.image_label.pack(padx=10, pady=(10, 5))
        self.image_label.bind("<Button-1>", lambda e: self.show_preview())
        
        # Wallpaper name
        name = self.format_name(wallpaper_data['name'])
        self.name_label = ctk.CTkLabel(
            self.card,
            text=name,
            font=("Arial", 12, "bold"),
            wraplength=230,
            cursor="hand2"
        )
        self.name_label.pack(pady=(5, 5))
        self.name_label.bind("<Button-1>", lambda e: self.show_preview())
        
        # Preview button
        self.preview_btn = ctk.CTkButton(
            self.card,
            text="👁️ Preview",
            width=220,
            command=self.show_preview,
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        self.preview_btn.pack(pady=(0, 10))
        
        # Load thumbnail in background
        threading.Thread(target=self.load_thumbnail, daemon=True).start()
    
    def format_name(self, filename):
        """Format filename to readable name"""
        name = filename.rsplit('.', 1)[0]
        for res in ['_4k', '_2k', '_1080p', '_1440p', '_2160p', '_8k']:
            name = name.replace(res, '')
        name = name.replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def load_thumbnail(self):
        """Load thumbnail image"""
        try:
            thumb_path = THUMBNAILS_DIR / self.wallpaper_data['name']
            
            if thumb_path.exists():
                image = Image.open(thumb_path)
            else:
                response = requests.get(self.wallpaper_data['download_url'], timeout=10)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content))
                
                image.thumbnail((250, 140), Image.Resampling.LANCZOS)
                image.save(thumb_path, "JPEG", quality=85)
            
            image = image.resize((250, 140), Image.Resampling.LANCZOS)
            
            self.thumbnail_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=(250, 140)
            )
            
            self.after(0, self.update_thumbnail)
            
        except Exception as e:
            print(f"Error loading thumbnail: {e}")
            self.after(0, lambda: self.image_label.configure(text="Failed to load"))
    
    def update_thumbnail(self):
        """Update thumbnail in UI"""
        if self.thumbnail_image:
            self.image_label.configure(image=self.thumbnail_image, text="")
    
    def show_preview(self):
        """Show preview window"""
        if self.on_preview_callback:
            self.on_preview_callback(self.wallpaper_data)


class ZWallpaperApp(ctk.CTk):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("ZWallpaper - Beautiful Wallpapers")
        self.geometry("1200x700")
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Data
        self.categories = {}
        self.current_category = "all"
        self.all_wallpapers = []
        self.current_wallpaper = None
        
        # Create UI
        self.create_ui()
        
        # Load wallpapers
        self.load_wallpapers()
    
    def create_ui(self):
        """Create the user interface"""
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Top bar
        top_bar = ctk.CTkFrame(main_container, height=60, fg_color="#1a1a1a")
        top_bar.pack(fill="x", pady=(0, 10))
        top_bar.pack_propagate(False)
        
        # Logo/Title
        title = ctk.CTkLabel(
            top_bar,
            text="🎨 ZWallpaper",
            font=("Arial", 24, "bold")
        )
        title.pack(side="left", padx=20, pady=10)
        
        # Search bar
        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="Search wallpapers...",
            width=300,
            height=35
        )
        self.search_entry.pack(side="left", padx=20, pady=10)
        self.search_entry.bind("<KeyRelease>", self.on_search)
        
        # Refresh button
        refresh_btn = ctk.CTkButton(
            top_bar,
            text="🔄 Refresh",
            width=100,
            height=35,
            command=self.refresh_wallpapers
        )
        refresh_btn.pack(side="right", padx=20, pady=10)
        
        # Content area with sidebar
        content_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        
        # Sidebar
        self.sidebar = ctk.CTkFrame(content_frame, width=200, fg_color="#1a1a1a")
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))
        self.sidebar.pack_propagate(False)
        
        # Sidebar title
        sidebar_title = ctk.CTkLabel(
            self.sidebar,
            text="Categories",
            font=("Arial", 16, "bold")
        )
        sidebar_title.pack(pady=(20, 10), padx=10)
        
        # Category buttons
        self.category_buttons = {}
        
        # All category
        btn = ctk.CTkButton(
            self.sidebar,
            text="📁 All",
            anchor="w",
            height=35,
            fg_color="#2b2b2b",
            hover_color="#3d3d3d",
            command=lambda: self.show_category("all")
        )
        btn.pack(fill="x", padx=10, pady=5)
        self.category_buttons["all"] = btn
        
        # Scrollable wallpaper grid
        self.scrollable_frame = ctk.CTkScrollableFrame(
            content_frame,
            fg_color="#0d0d0d",
            corner_radius=10
        )
        self.scrollable_frame.pack(side="left", fill="both", expand=True)
        
        # Status bar
        self.status_bar = ctk.CTkFrame(main_container, height=30, fg_color="#1a1a1a")
        self.status_bar.pack(fill="x", pady=(10, 0))
        self.status_bar.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="Ready",
            font=("Arial", 10)
        )
        self.status_label.pack(side="left", padx=20)
    
    def load_wallpapers(self):
        """Load wallpapers from Archive.org"""
        self.update_status("Loading wallpapers from Archive.org...")
        threading.Thread(target=self._load_wallpapers_worker, daemon=True).start()
    
    def _load_wallpapers_worker(self):
        """Worker thread for loading wallpapers from Archive.org"""
        try:
            # Fetch metadata from Archive.org - correct endpoint
            metadata_url = f"https://archive.org/metadata/{ARCHIVE_ITEM}"
            print(f"Fetching from: {metadata_url}")
            
            response = requests.get(metadata_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            print(f"Response keys: {data.keys() if isinstance(data, dict) else 'Not a dict'}")
            
            # Archive.org metadata structure: {"files": [...]}
            if not isinstance(data, dict):
                raise ValueError(f"Expected dict, got {type(data)}")
            
            files_data = data.get('files', [])
            print(f"Number of files found: {len(files_data)}")
            
            if not files_data:
                raise ValueError("No files found in Archive.org item. Make sure you uploaded wallpapers!")
            
            # Process each file
            for file in files_data:
                print(f"Processing file: {file.get('name', 'unknown')}")
                name = file['name']
                
                # Skip non-image files and metadata files
                if not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
                    print(f"Skipping non-image: {name}")
                    continue
                
                # Skip Archive.org metadata files
                if name.endswith('_files.xml') or name.endswith('_meta.xml') or name.endswith('_meta.sqlite'):
                    print(f"Skipping metadata: {name}")
                    continue
                
                # Extract category from path (e.g., "nature/sunset.jpg" -> "nature")
                parts = name.split('/')
                
                if len(parts) > 1:
                    category = parts[0]
                    filename = parts[-1]
                else:
                    category = 'uncategorized'
                    filename = name
                
                # Skip thumbnail directories
                if 'thumb' in category.lower() or 'thumb' in filename.lower():
                    continue
                
                wallpaper_data = {
                    'name': filename,
                    'category': category,
                    'download_url': f"{ARCHIVE_BASE_URL}{name}",
                    'path': name,
                    'size': file.get('size', 0)
                }
                
                if category not in self.categories:
                    self.categories[category] = []
                
                self.categories[category].append(wallpaper_data)
                self.all_wallpapers.append(wallpaper_data)
                print(f"Added wallpaper: {filename} in category: {category}")
            
            print(f"\nTotal wallpapers loaded: {len(self.all_wallpapers)}")
            print(f"Categories: {list(self.categories.keys())}")
            
            # Update UI on main thread
            self.after(0, self.populate_categories)
            self.after(0, self.display_wallpapers)
            self.after(0, lambda: self.update_status(f"Loaded {len(self.all_wallpapers)} wallpapers"))
            
        except Exception as ex:
            error_msg = str(ex)
            print(f"Error loading wallpapers: {error_msg}")
            import traceback
            traceback.print_exc()
            self.after(0, lambda msg=error_msg: self.update_status(f"Error: {msg}"))
    
    def populate_categories(self):
        """Populate category buttons in sidebar"""
        # Remove old category buttons (except "All")
        for name, btn in list(self.category_buttons.items()):
            if name != "all":
                btn.destroy()
        
        # Icons for categories
        icons = {
            'nature': '🌲',
            'abstract': '🎨',
            'cars': '🚗',
            'space': '🌌',
            'minimal': '✨',
            'anime': '🎌',
            'urban': '🏙️',
            'gaming': '🎮',
            'animals': '🦁',
            'architecture': '🏛️'
        }
        
        # Add category buttons
        for category in sorted(self.categories.keys()):
            icon = icons.get(category.lower(), '📁')
            count = len(self.categories[category])
            
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{icon} {category.title()} ({count})",
                anchor="w",
                height=35,
                fg_color="transparent",
                hover_color="#3d3d3d",
                command=lambda c=category: self.show_category(c)
            )
            btn.pack(fill="x", padx=10, pady=5)
            self.category_buttons[category] = btn
    
    def display_wallpapers(self, wallpapers=None):
        """Display wallpapers in grid"""
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if wallpapers is None:
            wallpapers = self.all_wallpapers
        
        if not wallpapers:
            no_results = ctk.CTkLabel(
                self.scrollable_frame,
                text="No wallpapers found",
                font=("Arial", 16)
            )
            no_results.pack(pady=50)
            return
        
        # Create grid
        current_row = None
        for i, wallpaper in enumerate(wallpapers):
            if i % 3 == 0:  # 3 columns
                current_row = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
                current_row.pack(fill="x", padx=10, pady=5)
            
            card = WallpaperCard(
                current_row,
                wallpaper,
                self.show_preview
            )
            card.pack(side="left", fill="both", expand=True)
    
    def show_category(self, category):
        """Show wallpapers from specific category"""
        self.current_category = category
        
        # Highlight selected category button
        for name, btn in self.category_buttons.items():
            if name == category:
                btn.configure(fg_color="#2b2b2b")
            else:
                btn.configure(fg_color="transparent")
        
        # Display wallpapers
        if category == "all":
            self.display_wallpapers(self.all_wallpapers)
        else:
            self.display_wallpapers(self.categories.get(category, []))
    
    def on_search(self, event=None):
        """Handle search input"""
        query = self.search_entry.get().lower()
        
        if not query:
            self.show_category(self.current_category)
            return
        
        # Filter wallpapers
        if self.current_category == "all":
            wallpapers = self.all_wallpapers
        else:
            wallpapers = self.categories.get(self.current_category, [])
        
        filtered = [w for w in wallpapers if query in w['name'].lower()]
        self.display_wallpapers(filtered)
    
    def refresh_wallpapers(self):
        """Refresh wallpaper list from Archive.org"""
        self.categories.clear()
        self.all_wallpapers.clear()
        self.load_wallpapers()
    
    def show_preview(self, wallpaper_data):
        """Show preview window for wallpaper"""
        PreviewWindow(
            self,
            wallpaper_data,
            self.on_wallpaper_applied,
            self.on_wallpaper_downloaded
        )
    
    def on_wallpaper_applied(self, wallpaper_name):
        """Callback when wallpaper is applied"""
        self.current_wallpaper = wallpaper_name
        self.update_status(f"Applied: {wallpaper_name}")
    
    def on_wallpaper_downloaded(self, download_path):
        """Callback when wallpaper is downloaded"""
        self.update_status(f"Downloaded to: {download_path}")
    
    def update_status(self, message):
        """Update status bar message"""
        self.status_label.configure(text=message)


def main():
    """Main entry point"""
    
    # Check if Archive.org item is configured
    if ARCHIVE_ITEM == "your-archive-item-name":
        print("=" * 60)
        print("CONFIGURATION REQUIRED")
        print("=" * 60)
        print("\nPlease update the following in the code:")
        print(f"  ARCHIVE_ITEM = 'your-actual-archive-item-identifier'")
        print("\nExample: If your Archive.org URL is:")
        print("  https://archive.org/details/my-wallpapers")
        print("Then set:")
        print("  ARCHIVE_ITEM = 'my-wallpapers'")
        print("\n" + "=" * 60)
        return
    
    # Start app
    app = ZWallpaperApp()
    app.mainloop()


if __name__ == "__main__":
    main()