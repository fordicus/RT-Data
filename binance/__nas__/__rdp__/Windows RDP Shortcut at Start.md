# Windows 11 RDP File Pinning Workaround

This folder contains `.rdp` files for accessing remote desktops, along with `.lnk` shortcut files used to pin them to the Start menu in Windows 11.

## Background

Windows 11 does not allow direct pinning of `.rdp` (Remote Desktop Protocol) files to the Start menu. To bypass this, the following workaround was used:

## Pinning `.rdp` Files to Start

### Steps

1. **Create Shortcuts**
   - For each `.rdp` file (`*.rdp`), create a shortcut (`*.lnk`).
   - Example:
     - `Nitro-AN515-54-External.rdp` → `Nitro-AN515-54-External.rdp.lnk`
     - `Nitro-AN515-54-Intranet.rdp` → `Nitro-AN515-54-Intranet.rdp.lnk`

2. **Move Shortcuts to Start Menu Programs Folder**
   - Copy the `.lnk` files to:
     ```
     C:\Users\<your-username>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs
     ```
   - This makes them visible in the Windows Start menu's searchable entries.

3. **Pin to Start**
   - Open Start, search for the shortcut name.
   - Right-click and select `Pin to Start`.

### Notes

- The `Programs - Shortcut.lnk` in this folder is a reference used to quickly access the Start Menu’s `Programs` directory.
- This method ensures `.rdp` sessions can be launched quickly via the Start menu without opening the Remote Desktop app manually.

## Files in This Folder

- `.rdp` files: Remote Desktop configurations
- `.lnk` files: Shortcuts for pinning
- `Programs - Shortcut.lnk`: Shortcut to the Start Menu programs folder
- `Ubuntu Remote Access Setup and Troubleshooting Guide.md`: Additional documentation (unrelated to the pinning process)

---

This workaround is simple, does not require admin privileges, and integrates cleanly into the Start experience.
