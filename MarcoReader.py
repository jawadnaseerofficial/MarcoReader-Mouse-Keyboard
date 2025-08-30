import time
import threading
from pynput import mouse, keyboard
from pynput.keyboard import Key, KeyCode
import tkinter as tk
from tkinter import ttk, messagebox

recorded_actions = []          
record_lock = threading.Lock() 
is_recording = False
is_playing = False

now = time.perf_counter

IGNORE_KEYS_FOR_SEC = 0.15
_last_toggle_time = 0.0


class MacroRecorderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Macro Recorder")
        self.root.geometry("560x640")
        self.root.resizable(False, False)
        self.root.config(bg='#121212')

        self.root.configure(bg="black")
        self.root.option_add("*TFrame*background", "black")
        self.root.option_add("*TLabel*background", "black")
        self.root.option_add("*TButton*background", "#1e1e1e")
        self.root.option_add("*TRadiobutton*background", "black")

        style = ttk.Style()
        style.theme_use("clam")
        default_font = ("Segoe UI", 10)
        bold_font = ("Segoe UI", 10, "bold")
        style.configure("TLabel", foreground="red", background="black", font=default_font)
        style.configure("TButton", foreground="red", background="#1e1e1e", font=bold_font, padding=6)
        style.map(
            "TButton",
            foreground=[("pressed", "red"), ("active", "orange")],
            background=[("pressed", "#333333"), ("active", "#2a2a2a")],
        )
        style.configure("TRadiobutton", foreground="red", background="black", font=("Segoe UI", 9))
        style.map("TRadiobutton", foreground=[("active", "orange")])

        self.status = tk.StringVar(value="🔴 Ready to record")
        self.repeat_mode = tk.StringVar(value="infinite")
        self.seconds = tk.IntVar(value=10)
        self.record_key_var = tk.StringVar(value="f9")  

        self.recording_hotkey = None  
        self.play_toggle_hotkey = (Key.f4,)  # ✅ FIXED: Now correctly uses Key.f4
        self.current_pressed = set()  

        self.control_widgets = []

        self.excluded_areas = []

        self._build_ui()
        self._start_listeners()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding="20")
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="🖱️ Keyboard & Mouse Macro Recorder", font=("Segoe UI", 14, "bold"), bg="black", fg="red").pack(pady=10)
        tk.Label(frame, textvariable=self.status, font=("Segoe UI", 10), bg="black", fg="red").pack(pady=5)

        ttk.Label(frame, text="⌨️ Recording Shortcut (e.g., f9, ctrl+r):").pack(anchor="w", pady=(5, 0))
        self.record_entry = ttk.Entry(frame, textvariable=self.record_key_var, font=("Segoe UI", 10))
        self.record_entry.pack(fill="x", pady=2)

        self.apply_btn = ttk.Button(frame, text="✅ Apply Shortcut", command=self.apply_shortcut)
        self.apply_btn.pack(pady=10, fill="x")

        self.shortcut_status = tk.Label(frame, text="Shortcut not active. Click 'Apply'.", font=("Segoe UI", 9), bg="black", fg="orange")
        self.shortcut_status.pack(pady=5)

        self.record_btn = ttk.Button(frame, text="🔷 Start Recording", command=self.start_recording_with_countdown)
        self.record_btn.pack(pady=10, fill="x")

        ttk.Label(frame, text="🔁 Repeat Mode:").pack(anchor="w", pady=(10, 0))
        ttk.Radiobutton(frame, text="Infinite Repeat", variable=self.repeat_mode, value="infinite").pack(anchor="w")
        ttk.Radiobutton(frame, text="Repeat for (seconds):", variable=self.repeat_mode, value="seconds").pack(anchor="w")

        seconds_frame = ttk.Frame(frame)
        seconds_frame.pack(anchor="w", padx=20, pady=5)
        ttk.Entry(seconds_frame, textvariable=self.seconds, width=10).pack(side="left")
        ttk.Label(seconds_frame, text="seconds").pack(side="left", padx=(5, 0))

        self.play_btn = ttk.Button(frame, text="▶️ Play Macro", command=self.toggle_play_macro, state="disabled")
        self.play_btn.pack(pady=15, fill="x")

        ttk.Button(frame, text="🧹 Clear Recording", command=self.clear_recording).pack(pady=5, fill="x")
        ttk.Button(frame, text="⏹️ Exit", command=self.exit_app).pack(pady=5, fill="x")

        footer = tk.Label(self.root, text="Developed by JAWAD NASEER", font=("Segoe UI", 12, "italic"), bg="black", fg="red")
        footer.pack(side="bottom", pady=10)

        self.control_widgets = [self.root, self.record_btn, self.play_btn, self.apply_btn, self.record_entry]

        self.root.after(50, self.update_excluded_areas)

    def update_excluded_areas(self):
        self.excluded_areas = []
        widgets = [self.root, self.record_btn, self.play_btn, self.apply_btn, self.record_entry]
        for widget in widgets:
            try:
                x1 = widget.winfo_rootx(); y1 = widget.winfo_rooty()
                x2 = x1 + widget.winfo_width(); y2 = y1 + widget.winfo_height()
                self.excluded_areas.append((x1, y1, x2, y2))
            except Exception:
                pass
       
        if self.root.winfo_exists():
            self.root.after(500, self.update_excluded_areas)

    @staticmethod
    def _token_from_key_event(key):
        """Normalize pynput key to a comparable token (Key for specials, lower char for letters)."""
        try:
            if hasattr(key, "char") and key.char is not None:
                return key.char.lower()
        except Exception:
            pass
        return key  

    @staticmethod
    def _token_from_text(part: str):
        """Convert text like 'ctrl', 'f9', 'a' into a token comparable to _token_from_key_event."""
        p = part.strip().lower()
        special_names = {
            "ctrl": Key.ctrl,
            "control": Key.ctrl,
            "alt": Key.alt,
            "shift": Key.shift,
            "cmd": Key.cmd,
            "super": Key.cmd,
            "win": Key.cmd,
            "esc": Key.esc,
            "escape": Key.esc,
            "space": Key.space,
            "enter": Key.enter,
            "return": Key.enter,
            "tab": Key.tab,
        }
        if p in special_names:
            return special_names[p]
     
        if p.startswith("f") and p[1:].isdigit():
            try:
                return getattr(Key, p)
            except AttributeError:
                pass
        
        if len(p) == 1:
            return p
      
        k = getattr(Key, p, None)
        return k if k is not None else p

    def parse_hotkey(self, key_string: str):
        parts = [self._token_from_text(s) for s in key_string.split("+") if s.strip()]
        return tuple(parts)

    def apply_shortcut(self):
        try:
            self.recording_hotkey = self.parse_hotkey(self.record_key_var.get())
            if not self.recording_hotkey:
                raise ValueError("Empty shortcut")
            self.shortcut_status.config(text="✅ Recording shortcut applied!", fg="lime")
        except Exception as e:
            messagebox.showerror("Invalid Shortcut", f"Could not parse: {e}")

    def matches_hotkey(self, pressed_set, hotkey_tuple):
        if not hotkey_tuple:
            return False
        return all(h in pressed_set for h in hotkey_tuple)

    def is_in_excluded_area(self, x, y):
        for (x1, y1, x2, y2) in self.excluded_areas:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return True
        return False

    def is_app_focused(self):
        w = self.root.focus_get()
        if not w:
            return False
        try:
            return w.winfo_toplevel() == self.root
        except Exception:
            return False

    
    def _start_listeners(self):
        def start_kb():
            with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
                listener.join()
        def start_mouse():
            with mouse.Listener(on_click=self.on_click) as listener:
                listener.join()
        threading.Thread(target=start_kb, daemon=True).start()
        threading.Thread(target=start_mouse, daemon=True).start()

    
    def on_press(self, key):
        global is_recording, is_playing, _last_toggle_time
        token = self._token_from_key_event(key)
        if token not in self.current_pressed:
            self.current_pressed.add(token)

        if self.recording_hotkey and not is_playing:
            if self.matches_hotkey(self.current_pressed, self.recording_hotkey):
                t = now()
                if t - _last_toggle_time > 0.25:
                    _last_toggle_time = t
                    if not is_recording:
                        self.root.after(0, self.start_recording_with_countdown)
                    else:
                        self.root.after(0, self.stop_recording)

        if self.play_toggle_hotkey:
            if self.matches_hotkey(self.current_pressed, self.play_toggle_hotkey):
                t = now()
                if t - _last_toggle_time > 0.25:  
                    _last_toggle_time = t
                    self.root.after(0, self.toggle_play_macro)

        if key == Key.esc:
            self.exit_app()
            return

        if is_recording:
            if self.is_app_focused() or (now() - _last_toggle_time) < IGNORE_KEYS_FOR_SEC:
                return
            with record_lock:
                recorded_actions.append(("press", now(), key))

    def on_release(self, key):
        token = self._token_from_key_event(key)
        self.current_pressed.discard(token)
        if is_recording:
            if self.is_app_focused() or (now() - _last_toggle_time) < IGNORE_KEYS_FOR_SEC:
                return
            with record_lock:
                recorded_actions.append(("release", now(), key))

    def on_click(self, x, y, button, pressed):
        if not is_recording:
            return
 
        if self.is_in_excluded_area(x, y):
            return
        with record_lock:
            recorded_actions.append(("click" if pressed else "unclick", now(), x, y, button))

    def start_recording_with_countdown(self):
        self.record_btn.config(state="disabled")
        self._countdown_val = 3
        self.status.set("🎯 Get ready... Starting in 3...")
        self.root.after(10, self._countdown_tick)

    def _countdown_tick(self):
        if self._countdown_val <= 0:
            self._start_actual_recording()
            return
        self.status.set(f"🎯 Recording starts in {self._countdown_val}... (Keep mouse/keyboard outside app)")
        self._countdown_val -= 1
        self.root.after(1000, self._countdown_tick)

    def _start_actual_recording(self):
        global is_recording
        self.root.update_idletasks()
        self.update_excluded_areas()
        with record_lock:
            recorded_actions.clear()
        is_recording = True
        self.play_btn.config(state="disabled")
        self.record_btn.config(text="🛑 Stop Recording", command=self.stop_recording, state="normal")
        self.status.set("🟢 Recording... Actions inside app are ignored.")

    def stop_recording(self):
        global is_recording
        if not is_recording:
            return
        is_recording = False
        self.status.set("✅ Recording stopped. Ready to play.")
        self.record_btn.config(text="🔷 Start Recording", command=self.start_recording_with_countdown, state="normal")
        self.play_btn.config(state="normal")

    def clear_recording(self):
        with record_lock:
            recorded_actions.clear()
        self.status.set("🧹 Cleared. Record something new.")
        self.play_btn.config(state="disabled")

    def toggle_play_macro(self):
        global is_playing
        if is_playing:
            is_playing = False
            self.play_btn.config(text="▶️ Play Macro (f4)")
            self.status.set("⏹️ Playback stopped.")
            return
    
        with record_lock:
            if not recorded_actions:
                messagebox.showwarning("No Macro", "Please record actions first!")
                return
            snapshot = list(recorded_actions)
        is_playing = True
        self.play_btn.config(text="⏹️ Stop Macro (f4)")
        self.status.set("▶️ Playback running...")
        threading.Thread(target=self._playback_loop, args=(snapshot,), daemon=True).start()

    def _playback_loop(self, actions_snapshot):
        global is_playing
        kb = keyboard.Controller()
        ms = mouse.Controller()
        start_time = actions_snapshot[0][1]
        repeat_mode = self.repeat_mode.get()
        duration = max(0, int(self.seconds.get() or 0))

        while is_playing:
            loop_start = now()
            for event in actions_snapshot:
                if not is_playing:
                    break
                event_type, event_time, *data = event
                delay = event_time - start_time
        
                while is_playing and (now() - loop_start) < delay:
                    time.sleep(0.005)
                if not is_playing:
                    break
                try:
                    if event_type == "press":
                        kb.press(data[0])
                    elif event_type == "release":
                        kb.release(data[0])
                    elif event_type == "click":
                        x, y, button = data
                        ms.position = (x, y)
                        ms.press(button)
                    elif event_type == "unclick":
                        x, y, button = data
                        ms.position = (x, y)
                        ms.release(button)
                except Exception as e:
                    print(f"Playback error: {e}")

            if repeat_mode == "seconds" and (now() - loop_start) >= duration:
                break

        is_playing = False
        self.play_btn.config(text="▶️ Play Macro (f4)")
        self.status.set("⏹️ Playback finished.")

    def exit_app(self):
        global is_playing, is_recording
        is_playing = False
        is_recording = False
        try:
            self.root.quit()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroRecorderApp(root)
    root.mainloop()