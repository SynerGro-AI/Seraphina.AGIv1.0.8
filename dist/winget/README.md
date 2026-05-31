# WinGet manifests (Windows Package Manager)

These manifests let users install Seraphina.AGI on Windows with:

```powershell
winget install SynerGro.SeraphinaAGI
```

## Status

- **Local validation:** ready (`winget validate --manifest .\SynerGro.SeraphinaAGI\1.0.8`)
- **Submitted to microsoft/winget-pkgs:** NOT YET — requires a public GitHub
  Release first so `InstallerUrl` resolves and `InstallerSha256` is real.

## Publishing checklist

1. Create a GitHub Release at tag `v1.0.8`. Attach a zip:

   ```powershell
   Compress-Archive -Path * -DestinationPath SeraphinaAGI-1.0.8.zip `
     -Exclude .git,.smoke-venv,*.glyph,prebuilt\*.glyph
   ```

   (Keep `prebuilt\*.glyph` if you want the demo artifacts in the zip.)

2. Capture the hash:

   ```powershell
   (Get-FileHash .\SeraphinaAGI-1.0.8.zip -Algorithm SHA256).Hash
   ```

3. Edit `SynerGro.SeraphinaAGI.installer.yaml`:
   - Replace `REPLACE_WITH_SHA256_OF_RELEASE_ZIP` with the captured hash.
   - Confirm the `InstallerUrl` matches the release asset URL.

4. Validate:

   ```powershell
   winget validate --manifest .\SynerGro.SeraphinaAGI\1.0.8
   ```

5. Fork https://github.com/microsoft/winget-pkgs, copy this `SynerGro/`
   directory under `manifests/s/SynerGro/SeraphinaAGI/1.0.8/`, and open a PR.
