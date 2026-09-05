# Dental Clinic — installing and using the app

A guide for the clinic. No technical knowledge needed.

---

## What this app is

It keeps the clinic's records on **this computer**: patients, appointments,
treatment notes, the tooth chart, X-rays, bills and lab work.

**Everything stays on this computer.** Nothing is sent to the internet, and the app
works even when the internet is down. There is no password to remember and no
monthly fee.

---

## Installing it

1. Double-click **`Dental Clinic_0.1.0_x64-setup.exe`**.

2. **Windows will show a blue warning box** saying "Windows protected your PC".
   This is normal and does not mean anything is wrong — it appears for any app
   that has not paid Microsoft for a certificate.

   Click **More info**, then **Run anyway**.

3. The installer runs on its own. It takes about a minute.

4. When it finishes you will have a **Dental Clinic** icon on the desktop.

You do **not** need to be an administrator, and it will not ask for a password.

---

## Opening the app

Double-click the **Dental Clinic** icon.

- **The very first time**, it takes about a minute while it sets itself up. You
  will see a "Starting the clinic app…" screen. **Leave it open** — it is working.
- **Every time after that**, it opens in a few seconds.

When you close the window, the app shuts down completely.

---

## Where the clinic's records are kept

Two folders, both inside `C:\Users\<your name>\AppData\Local\ClinicApp`:

| Folder | What is in it |
|---|---|
| `pgdata` | Patients, appointments, notes, bills, the tooth chart |
| `uploads` | X-rays and photos |

**Do not move, rename or delete these folders.** You do not need to open them.

Uninstalling the app does **not** delete them, so the records survive a reinstall.

---

## ⚠️ Backups — please read this part

**The clinic's entire records are on one computer's hard disk.** If that disk
fails, and there is no copy anywhere else, the records are gone. Hard disks do
fail, usually without warning.

### What happens automatically

**The app backs itself up every morning, the first time you open it.** It happens
in the background, so the app opens at its normal speed and you do not have to
wait or click anything.

It backs up once a day. Opening and closing the app several times in one day will
not make extra copies.

Each backup holds both the records and the X-rays, in one file, in:

```
C:\Users\<your name>\AppData\Local\ClinicApp\backups
```

It keeps the last 30 days and deletes older ones.

> Backing up when the app opens means yesterday's finished work is saved before
> today's begins - and the clinic PC is switched on, which is the one moment a
> backup can actually run.

### What you must do — once a week

**The automatic backup is on the same disk as the records.** If that disk dies,
the backups die with it. So a copy has to leave the computer.

**Once a week, please:**

1. Plug in a pen drive.
2. Open the `backups` folder above.
3. Copy the **newest** file (they are named by date) onto the pen drive.
4. Keep the pen drive somewhere other than next to the computer.

A cloud folder — Google Drive, OneDrive — works just as well, and is less to
remember. Copying one file a week is the whole job.

> **This is the single most important habit with this app.** Everything else can
> be fixed. Lost records cannot.

---

## Moving to a new computer

Everything the app knows lives in **one backup file**, so moving to a new
computer is: install the app, then restore that file. It takes about five
minutes and **nothing is lost** - patients, appointments, bills, treatment
notes, the tooth chart and the X-rays all come across.

**This has been tested properly**: the app and all its data were deleted from a
computer, then rebuilt from a single backup file. Everything came back,
including the X-ray images.

### Before leaving the old computer

1. Open the app on the **old** computer (the backup needs it running).
2. Make a fresh backup so nothing from the last day is missed - double-click
   **`backup.exe`** in the app folder, or ask Rishi.
3. Copy the **newest** file from the `backups` folder onto a pen drive:
   `C:\Users\<your name>\AppData\Local\ClinicApp\backups`

### On the new computer

1. Install the app the normal way (`Dental Clinic_0.1.0_x64-setup.exe`).
2. **Open it once, then close it.** This lets it set itself up. It will be empty
   - that is expected, do not worry.
3. Restore the backup from the pen drive. Rishi runs:
   `"%LOCALAPPDATA%\Dental Clinic\backup.exe" --restore "E:\clinic-backup-....zip"`
   (replace `E:` with the pen drive letter, and use the real file name)
4. It asks you to type **RESTORE** to confirm. That is deliberate - it replaces
   everything currently in the app.
5. Close and reopen the app. All the records will be there.
6. Nothing else to set up - the app backs itself up when opened, so that starts
   working on the new computer by itself.

### The old computer

Keep it, switched off, for a few weeks until you are sure the new one is fine.
It is a free extra copy of everything. Wipe it only after that.

---

## If something goes wrong

**The app will not open, or the starting screen never finishes**
Restart the computer and try again. That clears almost everything.

**"Windows protected your PC" appears again after an update**
Same as during installation: **More info** → **Run anyway**.

**Something looks wrong in the records**
Stop using the app and call Rishi **before** entering more. The nightly backup
means yesterday's version can be brought back — but only if you do not overwrite
it first.

**The computer has died and you need the records on a new one**
1. Install the app on the new computer.
2. Copy the newest backup file from the pen drive onto it.
3. Call Rishi — restoring takes one command and a couple of minutes.

---

## For Rishi — the technical bits

**Backups**

```powershell
# make one now
"$env:LOCALAPPDATA\Dental Clinic\backup.exe"

# list them
"$env:LOCALAPPDATA\Dental Clinic\backup.exe" --list

# check a backup is readable, WITHOUT restoring it
"$env:LOCALAPPDATA\Dental Clinic\backup.exe" --verify <file.zip>

# restore (destructive — asks for confirmation)
"$env:LOCALAPPDATA\Dental Clinic\backup.exe" --restore <file.zip>
```

The app must be running for any of these — they connect to its database.

**Automatic backups**

`start_daily_backup()` in `packaging/launcher.py` runs on app startup, after the
services are up, on a daemon thread so it never delays the window. It skips if a
`clinic-backup-<today>-*.zip` already exists, so it is at most once a day.

**The 9pm scheduled task was REMOVED and should not come back.** Two reasons: the
clinic closes at 4-5pm so the PC was off and Windows deferred the task to the next
boot anyway; and a backup needs Postgres *running*, which at 9pm on a closed
clinic it is not. `install_backup_task.ps1` is now only a cleanup script that
unregisters the old task on machines that already have it.

**Ports** (all on 127.0.0.1, nothing is exposed to the network): Postgres 55432,
backend 55433, frontend 55434.

**Backup format** — a plain `.zip` holding `database.dump` (pg_dump custom
format) and `uploads/`. Deliberately boring: recoverable with standard tools,
by somebody who is not me, years from now.

**A restore has been rehearsed**, not assumed — database and X-rays wiped, then
restored from a backup, with the patient, chart entry, paid invoice and X-ray
bytes all verified back. That was the gate `BUILD_PLAN.md` §11 and step 8.3 set
before real patient data goes in.

**What is still not covered:** getting a copy off the machine is manual and
therefore the weakest link. If the weekly pen-drive habit does not hold, automate
it (rclone to Google Drive's free tier is the obvious ₹0 answer) before it
matters.
