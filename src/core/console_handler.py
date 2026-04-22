import os
import shlex
import subprocess
import sys
import threading
from typing import Callable, Optional

class ConsoleHandler:
    """
    Handles command execution from the internal DowP console.
    Supports running integrated binaries (yt-dlp, ffmpeg) and custom commands (dp).
    """
    def __init__(self, bin_dir: str, ffmpeg_bin_dir: str):
        self.bin_dir = bin_dir
        self.ffmpeg_bin_dir = ffmpeg_bin_dir
        self._cmd_process: Optional[subprocess.Popen] = None
        self._output_callback: Optional[Callable[[str, str], None]] = None
        self._finish_callback: Optional[Callable[[], None]] = None

    def connect_callbacks(self, output_cb: Callable[[str, str], None], finish_cb: Callable[[], None]):
        """Connects the interface functions that will receive the text and completion notifications."""
        self._output_callback = output_cb
        self._finish_callback = finish_cb

    def _print_to_console(self, text: str, tag: str = "normal"):
        if self._output_callback:
            self._output_callback(text, tag)

    def execute_command(self, raw_command: str):
        """Main entry point for processing a command."""
        raw = raw_command.strip()
        if not raw:
            self._on_finished()
            return

        # Reflect the command entered by the user in cyan color
        self._print_to_console(f"\n> {raw}\n", tag="user_command")

        parts = raw.split()
        tool = parts[0].lower()
        args = parts[1:]

        # Check for model list flag --m
        if len(args) == 1 and args[0] == "--m":
            if tool in ("w2x", "srmd", "upy"):
                self._list_models(tool)
                self._on_finished()
                return

        if tool == "ffmpeg":
            self._run_ffmpeg(raw[len("ffmpeg"):].strip())
        elif tool == "yt-dlp":
            self._run_ytdlp(raw[len("yt-dlp"):].strip())
        elif tool == "w2x":
            self._run_upscaling_tool("waifu2x", raw[len("w2x"):].strip())
        elif tool == "srmd":
            self._run_upscaling_tool("srmd", raw[len("srmd"):].strip())
        elif tool == "upy":
            self._run_upscaling_tool("upscayl", raw[len("upy"):].strip())
        elif tool == "dp":
            self._run_dp_command(args)
        else:
            self._print_to_console(
                f"\n[Console] Tool not recognized: '{tool}'.\n"
                f"          Available commands: dp, ffmpeg, yt-dlp, w2x, srmd, upy\n\n",
                tag="warning"
            )
            self._on_finished()

    def _run_ffmpeg(self, args_str: str):
        ffmpeg_exe = os.path.join(self.ffmpeg_bin_dir, "ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
        cmd = [ffmpeg_exe] + self._safe_split(args_str)
        self._start_process(cmd, "ffmpeg")

    def _run_ytdlp(self, args_str: str):
        ytdlp_zip = os.path.join(self.bin_dir, "ytdlp", "yt-dlp.zip")
        if not os.path.exists(ytdlp_zip):
            self._print_to_console(f"\n[ERROR] yt-dlp.zip not found in: {ytdlp_zip}\n", tag="error")
            self._on_finished()
            return
            
        python_exe = sys.executable
        cmd = [python_exe, ytdlp_zip] + self._safe_split(args_str)
        self._start_process(cmd, "yt-dlp")

    def _run_upscaling_tool(self, tool_key: str, args_str: str):
        """Runs one of the ncnn-vulkan upscaling tools."""
        upscaling_base = os.path.join(self.bin_dir, "models", "upscaling")
        
        if tool_key == "waifu2x":
            exe_name = "waifu2x-ncnn-vulkan.exe" if os.name == 'nt' else "waifu2x-ncnn-vulkan"
            tool_label = "Waifu2x"
        elif tool_key == "srmd":
            exe_name = "srmd-ncnn-vulkan.exe" if os.name == 'nt' else "srmd-ncnn-vulkan"
            tool_label = "SRMD"
        elif tool_key == "upscayl":
            exe_name = "upscayl-bin.exe" if os.name == 'nt' else "upscayl-bin"
            tool_label = "Upscayl"
        else:
            return

        exe_path = os.path.join(upscaling_base, tool_key, exe_name)
        if not os.path.exists(exe_path):
            self._print_to_console(f"\n[ERROR] Binary not found: {exe_path}\n", tag="error")
            self._on_finished()
            return

        cmd = [exe_path] + self._safe_split(args_str)
        self._start_process(cmd, tool_label)

    def _list_models(self, tool: str):
        """Universal model scanner that explores the tool's directory for model folders and files."""
        from src.core.constants import UPSCAYL_MODELS_MAP
        upscaling_base = os.path.join(self.bin_dir, "models", "upscaling")
        
        tool_dirs = {"upy": "upscayl", "w2x": "waifu2x", "srmd": "srmd"}
        tool_key = tool_dirs.get(tool)
        if not tool_key: return
        
        tool_path = os.path.join(upscaling_base, tool_key)
        if not os.path.exists(tool_path):
            self._print_to_console(f"\n[ERROR] Tool path not found: {tool_path}\n", tag="error")
            return

        self._print_to_console(f"\n=== Scanning {tool.upper()} Models ===\n")
        
        found_any = False
        
        # 1. Search for any items in the tool root
        try:
            items = os.listdir(tool_path)
        except Exception as e:
            self._print_to_console(f"[ERROR] Could not read directory: {e}\n", tag="error")
            return

        # 2. Check for folders at root that could be models or containers
        for item in items:
            item_path = os.path.join(tool_path, item)
            if not os.path.isdir(item_path):
                continue
            
            # Identify if this is a models folder (starts with 'models')
            if item.lower().startswith("models"):
                try:
                    content = os.listdir(item_path)
                except: continue
                
                # Check for .param files (File-based engines like SRMD/Upscayl)
                params = sorted([f[:-6] for f in content if f.endswith(".param")])
                
                # Check for subdirectories (Folder-based engines like Waifu2x)
                subdirs = sorted([d for d in content if os.path.isdir(os.path.join(item_path, d))])
                
                if params:
                    self._print_to_console(f"\n[{item}] (Model files found):\n")
                    for p in params:
                        friendly = UPSCAYL_MODELS_MAP.get(p, "") if tool == "upy" else ""
                        desc = f" ({friendly})" if friendly else ""
                        self._print_to_console(f" - {p:<30}{desc}\n")
                    found_any = True
                
                elif subdirs:
                    self._print_to_console(f"\n[{item}] (Model folders found):\n")
                    for d in subdirs:
                        self._print_to_console(f" - {d}\n")
                    found_any = True
                
                elif item.startswith("models-") and tool == "w2x":
                    # For Waifu2x, the folder itself is the entry
                    if not found_any:
                        self._print_to_console(f"\n[Found Engines]:\n")
                    self._print_to_console(f" - {item}\n")
                    found_any = True

        if not found_any:
            self._print_to_console(f"\n[Console] No models detected in: {tool_path}\n", tag="warning")
        
        self._print_to_console("\n")

    def _run_dp_command(self, args: list[str]):
        """Handles DowP internal commands."""
        if not args or args[0] in ("help", "-h", "--help"):
            self._print_dp_help()
            self._on_finished()
            return
            
        subcommand = args[0].lower()
        # TODO: Implement subcommands like info, etc.
        self._print_to_console(f"\n[DP] Subcommand '{subcommand}' not implemented yet.\n\n", tag="warning")
        self._on_finished()

    def _print_dp_help(self):
        help_text = (
            "Usage: [tool] [options...]\n\n"
            "DowP Commands:\n"
            "  dp -h, help            Show this help message.\n\n"
            "General Options:\n"
            "  ffmpeg                 Integrated FFmpeg engine.\n"
            "  yt-dlp                 Integrated yt-dlp engine.\n\n"
            "Upscaling Options:\n"
            "  upy                    Upscayl Global Engine\n"
            "  w2x                    Waifu2x Engine\n"
            "  srmd                   SRMD Engine\n"
            "  [tool] --m             List available models for that engine\n"
        )
        self._print_to_console(help_text, tag="normal")

    def _safe_split(self, args_str: str) -> list[str]:
        try:
            return shlex.split(args_str)
        except ValueError:
            return args_str.split()

    def _start_process(self, cmd: list[str], tool_label: str):
        def _run():
            import time
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                self._cmd_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1 # Line buffered
                )
                
                output_buffer = []
                last_flush_time = time.time()
                
                # Optimized chunked reading
                while True:
                    # Read up to 4KB at once
                    chunk = self._cmd_process.stdout.read(4096)
                    if not chunk:
                        break
                        
                    output_buffer.append(chunk)
                    
                    # Flush to UI every 100ms for heavy outputs
                    current_time = time.time()
                    if current_time - last_flush_time > 0.1:
                        self._print_to_console("".join(output_buffer), tag="normal")
                        output_buffer = []
                        last_flush_time = current_time
                
                # Final flush
                if output_buffer:
                    self._print_to_console("".join(output_buffer), tag="normal")
                    
                exit_code = self._cmd_process.wait()
                self._print_to_console(
                    f"\n[{tool_label}] Process finished (code: {exit_code})\n",
                    tag="normal"
                )
            except FileNotFoundError:
                self._print_to_console(f"\n[ERROR] Executable not found: {cmd[0]}\n", tag="error")
            except Exception as e:
                self._print_to_console(f"\n[ERROR] {e}\n", tag="error")
            finally:
                self._cmd_process = None
                self._on_finished()

        threading.Thread(target=_run, daemon=True).start()

    def cancel_process(self):
        """Terminates the running subprocess if it exists."""
        if self._cmd_process and self._cmd_process.poll() is None:
            try:
                self._cmd_process.terminate()
                self._print_to_console("\n[Console] Process canceled by user.\n", tag="warning")
            except Exception as e:
                print(f"WARNING [Console]: Could not cancel process: {e}")

    def _on_finished(self):
        if self._finish_callback:
            self._finish_callback()
