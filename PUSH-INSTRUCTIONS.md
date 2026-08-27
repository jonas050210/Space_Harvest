# Push this repo to your GitHub (owner's PC)

The sandbox has no GitHub credentials, so the final push happens where you are
logged in. The local repo here already has one clean commit on `main`
(`phase 1 (agent 1): ...`, 277 files; `.venv/`, `*.zip`, `logs/*.png` ignored).

## One-time on github.com
Create an empty repository named `asteroid-colony-proto` (no README/license).

## Then, in this folder
```bash
git remote add origin https://github.com/jonas050210/asteroid-colony-proto.git
git push -u origin main
```

Agents 2/3 add commits; they push the same way (`git push`).
