"""GUI application to browse Plex libraries and manage ClearLogos."""
import io
import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Iterator, List, Optional, Tuple

import requests
from PIL import Image, ImageTk
from plexapi.exceptions import BadRequest
from plexapi.server import PlexServer

CONFIG_FILE = "config.json"
POSTER_MAX_SIZE = (300, 450)
LOGO_MAX_SIZE = (400, 200)
REQUEST_TIMEOUT = 20


def load_config() -> Tuple[Optional[str], Optional[str]]:
    """Load Plex server connection details from the JSON config file."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        messagebox.showerror("Configuration", f"Configuration file '{CONFIG_FILE}' not found.")
        return None, None
    except json.JSONDecodeError as exc:
        messagebox.showerror("Configuration", f"Could not parse '{CONFIG_FILE}': {exc}")
        return None, None

    url = config.get("plex_url")
    token = config.get("plex_token")
    if not url or not token or token == "YOUR_PLEX_TOKEN_HERE":
        messagebox.showerror(
            "Configuration",
            "Please provide both 'plex_url' and 'plex_token' in the configuration file.",
        )
        return None, None
    return url, token


class ClearLogoApp:
    """Tkinter GUI for iterating Plex items and updating ClearLogos."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Plex ClearLogo Browser")
        self.root.geometry("900x700")

        self.status_var = tk.StringVar()
        self.info_var = tk.StringVar()
        self.logo_info_var = tk.StringVar()

        self.poster_photo: Optional[ImageTk.PhotoImage] = None
        self.logo_photo: Optional[ImageTk.PhotoImage] = None

        self.plex: Optional[PlexServer] = None
        self.item_iter: Optional[Iterator] = None
        self.current_item = None
        self.session = requests.Session()

        self._build_ui()
        self._initialize_connection()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        header = tk.Label(self.root, text="Plex ClearLogo Browser", font=("Segoe UI", 18, "bold"))
        header.pack(pady=(10, 5))

        info_label = tk.Label(self.root, textvariable=self.info_var, font=("Segoe UI", 12))
        info_label.pack(pady=(0, 5))

        images_frame = tk.Frame(self.root)
        images_frame.pack(pady=10)

        self.poster_label = tk.Label(images_frame, text="Poster not available", width=40, height=25, bd=2, relief=tk.GROOVE)
        self.poster_label.pack(side=tk.LEFT, padx=10)

        self.logo_label = tk.Label(images_frame, text="Logo not available", width=40, height=15, bd=2, relief=tk.GROOVE)
        self.logo_label.pack(side=tk.LEFT, padx=10)

        logo_info_label = tk.Label(self.root, textvariable=self.logo_info_var, font=("Segoe UI", 10))
        logo_info_label.pack(pady=(0, 10))

        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(pady=5)

        self.keep_button = tk.Button(buttons_frame, text="Keep Logo (Next)", command=self.next_item, width=18)
        self.keep_button.pack(side=tk.LEFT, padx=5)

        self.change_button = tk.Button(buttons_frame, text="Change Logo", command=self.change_logo, width=18)
        self.change_button.pack(side=tk.LEFT, padx=5)

        self.skip_button = tk.Button(buttons_frame, text="Skip Item", command=self.next_item, width=18)
        self.skip_button.pack(side=tk.LEFT, padx=5)

        status_label = tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10), fg="#555555")
        status_label.pack(pady=(10, 5))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ Connection --
    def _initialize_connection(self) -> None:
        url, token = load_config()
        if not url or not token:
            self.disable_controls()
            return

        try:
            self.status_var.set("Connecting to Plex server...")
            self.plex = PlexServer(url, token, timeout=30)
        except Exception as exc:  # pragma: no cover - network interaction
            messagebox.showerror("Connection", f"Failed to connect to Plex server: {exc}")
            self.disable_controls()
            return

        sections = [section for section in self.plex.library.sections() if section.type in ("movie", "show")]
        if not sections:
            messagebox.showinfo("Libraries", "No movie or show libraries were found on the server.")
            self.disable_controls()
            return

        self.item_iter = self._iter_items(sections)
        self.status_var.set(f"Connected to {self.plex.friendlyName}. Loading items...")
        self.root.after(100, self.next_item)

    @staticmethod
    def _iter_items(sections) -> Iterator:
        for section in sections:
            try:
                for item in section.all():
                    yield item
            except Exception as exc:  # pragma: no cover - network interaction
                print(f"Error loading items from {section.title}: {exc}")
                continue

    # ------------------------------------------------------------- Controls --
    def disable_controls(self) -> None:
        self.keep_button.config(state=tk.DISABLED)
        self.change_button.config(state=tk.DISABLED)
        self.skip_button.config(state=tk.DISABLED)

    def enable_controls(self) -> None:
        self.keep_button.config(state=tk.NORMAL)
        self.change_button.config(state=tk.NORMAL)
        self.skip_button.config(state=tk.NORMAL)

    # ----------------------------------------------------------- Navigation --
    def next_item(self) -> None:
        if not self.item_iter:
            return
        try:
            item = next(self.item_iter)
        except StopIteration:
            self.info_var.set("All items processed.")
            self.logo_info_var.set("")
            self.poster_label.config(image="", text="No more items")
            self.logo_label.config(image="", text="No more items")
            self.status_var.set("Completed browsing all items.")
            self.disable_controls()
            return

        self.show_item(item)

    def show_item(self, item) -> None:
        self.current_item = item
        title = getattr(item, "title", "Unknown Title")
        year = getattr(item, "year", "") or ""
        section_title = ""
        try:
            section_title = item.section().title
        except Exception:
            section_title = ""

        if year:
            display_title = f"{title} ({year})"
        else:
            display_title = title

        if section_title:
            display_title += f" — {section_title}"

        self.info_var.set(display_title)
        self.logo_info_var.set("Loading logo information...")
        self.poster_label.config(image="", text="Loading poster...")
        self.logo_label.config(image="", text="Loading logo...")
        self.status_var.set("Fetching artwork...")
        self.disable_controls()

        threading.Thread(target=self._load_artwork, args=(item,), daemon=True).start()

    # ------------------------------------------------------------- Artwork --
    def _load_artwork(self, item) -> None:
        poster_bytes = self._download_image(self._poster_url(item))
        logo_bytes, logo_details = self._download_logo(item)
        self.root.after(0, lambda: self._update_artwork(poster_bytes, logo_bytes, logo_details))

    def _poster_url(self, item) -> Optional[str]:
        for attr in ("posterUrl", "thumbUrl"):
            url = getattr(item, attr, None)
            if url:
                return url
        thumb = getattr(item, "thumb", None)
        if thumb and self.plex:
            return self.plex.url(thumb)
        return None

    def _download_logo(self, item) -> Tuple[Optional[bytes], str]:
        if not self.plex:
            return None, ""
        logo_text = "No ClearLogo assigned."
        try:
            logos: List = item.logos()
        except Exception as exc:  # pragma: no cover - network interaction
            return None, f"Unable to load logos: {exc}"

        selected_logo = next((logo for logo in logos if getattr(logo, "selected", False)), None)
        if not selected_logo and logos:
            selected_logo = logos[0]

        if not selected_logo:
            return None, "No ClearLogo assigned."

        logo_text = "Current logo provider: " + (selected_logo.provider or "Unknown")
        if getattr(selected_logo, "thumb", None):
            url = self.plex.url(selected_logo.thumb)
            return self._download_image(url), logo_text
        return None, logo_text

    def _download_image(self, url: Optional[str]) -> Optional[bytes]:
        if not url:
            return None
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.content
        except Exception:
            return None

    def _update_artwork(self, poster_bytes: Optional[bytes], logo_bytes: Optional[bytes], logo_text: str) -> None:
        self.poster_photo = self._bytes_to_photo(poster_bytes, POSTER_MAX_SIZE)
        if self.poster_photo:
            self.poster_label.config(image=self.poster_photo, text="")
        else:
            self.poster_label.config(image="", text="Poster not available")

        self.logo_photo = self._bytes_to_photo(logo_bytes, LOGO_MAX_SIZE)
        if self.logo_photo:
            self.logo_label.config(image=self.logo_photo, text="")
        else:
            self.logo_label.config(image="", text="Logo not available")

        self.logo_info_var.set(logo_text)
        self.status_var.set("Ready")
        self.enable_controls()

    @staticmethod
    def _bytes_to_photo(data: Optional[bytes], max_size: Tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
        if not data:
            return None
        try:
            image = Image.open(io.BytesIO(data))
            image.thumbnail(max_size, Image.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    # -------------------------------------------------------------- Actions --
    def change_logo(self) -> None:
        if not self.current_item:
            return

        url = simpledialog.askstring("Change ClearLogo", "Enter the URL of the new ClearLogo image:")
        if not url:
            self.status_var.set("Logo update cancelled.")
            return
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showerror("Invalid URL", "Please enter a valid http or https URL.")
            return

        self.status_var.set("Uploading new ClearLogo...")
        self.disable_controls()
        threading.Thread(target=self._upload_logo, args=(self.current_item, url), daemon=True).start()

    def _upload_logo(self, item, url: str) -> None:
        try:
            item.uploadLogo(url=url)
        except BadRequest as exc:  # pragma: no cover - network interaction
            self.root.after(0, lambda: self._handle_upload_error(f"Upload failed: {exc}"))
            return
        except AttributeError as exc:  # pragma: no cover - network interaction
            self.root.after(0, lambda: self._handle_upload_error(str(exc)))
            return
        except Exception as exc:  # pragma: no cover - network interaction
            self.root.after(0, lambda: self._handle_upload_error(f"Unexpected error: {exc}"))
            return

        try:
            item.reload()
        except Exception:
            pass
        self.root.after(0, lambda: self._handle_upload_success(item))

    def _handle_upload_error(self, message: str) -> None:
        messagebox.showerror("Upload", message)
        self.status_var.set("Upload failed.")
        self.enable_controls()

    def _handle_upload_success(self, item) -> None:
        self.status_var.set("Logo updated successfully.")
        self.show_item(item)

    # --------------------------------------------------------------- Events --
    def on_close(self) -> None:
        self.session.close()
        self.root.destroy()

    # ------------------------------------------------------------- Runtime --
    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = ClearLogoApp()
    app.run()
