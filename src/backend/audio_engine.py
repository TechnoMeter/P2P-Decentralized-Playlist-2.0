import pygame
import os

class AudioEngine:
    """Handles local audio playback using pygame. Supports seeking, pausing, and volume."""
    
    def __init__(self, logger_callback=None):
        self.logger = logger_callback
        self.is_playing = False
        self.is_paused = False
        
        # Track time manually because pygame.mixer.music.get_pos() resets on seek/play
        self.start_offset = 0.0 
        
        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(0.7)
            self.log("Audio Engine initialized.")
        except Exception as e:
            self.log(f"Failed to initialize audio: {e}")

    def log(self, text):
        if self.logger: self.logger(f"[Audio] {text}")

    def play_song(self, song_path, start_time=0):
        """Plays a song, optionally starting from a specific offset in seconds."""
        if not song_path or not os.path.exists(song_path):
            self.log(f"Playback error: File not found at {song_path}")
            return False

        try:
            pygame.mixer.music.load(song_path)
            pygame.mixer.music.play(start=start_time)
            
            self.is_playing = True
            self.is_paused = False
            self.start_offset = start_time
            
            if start_time > 0:
                self.log(f"Resuming: {os.path.basename(song_path)} at {start_time:.1f}s")
            else:
                self.log(f"Playing: {os.path.basename(song_path)}")
            return True
        except Exception as e:
            self.log(f"Pygame error: {e}")
            return False

    def toggle_pause(self):
        """Toggles between pause and unpause."""
        if not self.is_playing: return False
        
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.log("Resumed playback.")
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.log("Paused playback.")
        return self.is_paused

    def seek(self, position_seconds, file_path):
        """Seeks to a specific timestamp in seconds."""
        if not self.is_playing: return
        
        # Pygame seek implementation often requires reloading for MP3s/Variable bitrates
        # Using the play(start=...) method is more robust across formats than set_pos
        self.play_song(file_path, start_time=position_seconds)

    def get_current_pos(self):
        """Returns the current playback position in seconds, accounting for seeks."""
        if not self.is_playing: return 0
        
        try:
            # get_pos returns milliseconds since last 'play' call
            # We must add the offset we started playing from
            current_ms = pygame.mixer.music.get_pos()
            if current_ms == -1: return 0
            return self.start_offset + (current_ms / 1000.0)
        except:
            return 0

    def set_volume(self, volume):
        """Sets the music volume (0.0 to 1.0)."""
        try:
            pygame.mixer.music.set_volume(volume)
        except:
            pass

    def is_busy(self):
        """Returns True if audio is actively mixing (playing)."""
        try:
            return pygame.mixer.music.get_busy() or self.is_paused
        except:
            return False

    def stop(self):
        pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self.start_offset = 0