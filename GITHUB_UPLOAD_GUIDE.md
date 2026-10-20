# GitHub upload guide (safe, step by step)

This guide is for putting the **source code** in your own GitHub account. It does not deploy or run the bot by itself; Oracle Cloud deployment is described in `README.md`.

## Before you start

- Use the `anime-manga-tracker-github-ready.zip` archive provided with this project, or the project folder extracted from it.
- Do **not** upload your real `.env`, Discord bot token, API keys, SSH private key, live database, backups, or logs.
- The included `.env.example` is safe to upload because it contains a placeholder, not your token.
- `.gitignore` helps prevent accidental additions, but it cannot protect secrets that you manually paste into another file. Review the file list before publishing.

## Method A — GitHub Desktop (recommended for beginners on Windows/macOS)

1. Download and extract the project ZIP on your computer.
2. Install GitHub Desktop from <https://desktop.github.com/> and sign in to your GitHub account.
3. On GitHub.com, click **New repository**. Name it `anime-manga-tracker`. Choose **Private** if you want to limit who can see the source. Do not initialize it with a README, license, or `.gitignore` because these are already in this project.
4. In GitHub Desktop, choose **File → Add Local Repository**. Select the extracted `anime-manga-tracker` folder. If it says it is not a Git repository, choose the option to create a repository there; keep the project folder as the local path.
5. Review the changed-files list. Confirm `.env`, any `*.db`/`*.sqlite*`, SSH keys, logs, and backups are **not** listed. If a real secret appears, stop and remove it before proceeding.
6. Enter a summary such as `Initial project import` and click **Commit to main**.
7. Click **Publish repository**. Choose the repository you created and whether it should be private. Publish it.
8. Open the repository on GitHub.com and inspect its file list. You should see `README.md`, `.gitignore`, `.env.example`, `bot.py`, `config.py`, `bot/`, `tests/`, `deploy/`, requirements files, and audit documents. You should **not** see `.env`, database files, or private keys.

If you create the local repository in step 4, ensure its remote points to the GitHub repository you created. GitHub Desktop will guide you if it needs to connect/publish it.

## Method B — Git from a terminal

Install Git from <https://git-scm.com/downloads>, extract the ZIP, open a terminal in the `anime-manga-tracker` project folder, and run:

```bash
git init
git add .
git status --short
```

**Stop at this point and inspect `git status --short`.** Make sure no `.env`, database, logs, backup, token, or private key is listed. If anything sensitive appears, add an appropriate rule to `.gitignore`, then unstage it with `git rm --cached PATH` (replace `PATH` with that file) and verify again. If a secret has ever been committed, removing it from the next commit is not enough—rotate the secret and clean the history.

Then commit and connect the repository URL shown on GitHub:

```bash
git commit -m "Initial project import"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/anime-manga-tracker.git
git push -u origin main
```

Replace `YOUR-GITHUB-USERNAME` with your GitHub username. GitHub may ask you to authenticate using a browser or credential manager; do not put a password or token directly into these commands.

## Method C — Upload files on GitHub.com

The web uploader is less convenient for a project with many nested folders and hidden files. If you use it, create an empty repository, extract the ZIP locally, then use **Add file → Upload files** and drag the project contents into the browser. Check carefully that hidden files such as `.gitignore` are included. If the browser uploader skips folders or hidden files, use GitHub Desktop or Git instead. Do not upload the ZIP as a single file if you want GitHub to show the source files individually.

## Before every future push

- Never commit `.env` or paste the Discord token into source code, README, issues, screenshots, or commit messages.
- Keep `.env.example` placeholders only; no real values.
- Never commit your production SQLite database, backups, logs, or SSH/cloud credentials.
- Review staged files with `git status` before every commit.
- If a Discord token leaks, reset it in the Discord Developer Portal immediately. Deleting it later does not make the old token safe.

## What belongs in the repository?

**Include:** Python source (`bot.py`, `config.py`, `bot/`), `tests/`, `deploy/`, `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitignore`, `README.md`, `VERIFICATION.md`, and `SECURITY_AUDIT.md`.

**Exclude:** `.env`, live database files (`*.db`, `*.sqlite*`), `.venv/` or `venv/`, `__pycache__/`, `*.pyc`, logs, backups, real API keys, Discord tokens, SSH keys, and cloud credentials.
