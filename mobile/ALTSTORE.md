# Install MLB Edge IPA with AltStore

This Mac does **not** have full Xcode, so the IPA has to be built in the cloud with Expo EAS. AltStore will re-sign it with your Apple ID when you install.

## One-time setup

1. Create a free account at https://expo.dev if you don’t have one.
2. In Terminal:

```bash
cd /Users/henryblaney/Desktop/VIP/mlb-edge/mobile
npx eas-cli login
npx eas-cli build:configure   # only if prompted; eas.json is already here
```

3. First iOS build will ask for an **Apple ID** (the same one you use with AltStore is fine). EAS can manage certs/profiles for you — choose **Let Expo handle credentials**.

## Build the IPA

```bash
cd /Users/henryblaney/Desktop/VIP/mlb-edge/mobile
npm run build:ipa
```

When the build finishes, Expo prints a **download URL** for the `.ipa`. Save that file (AirDrop / Files / iCloud).

## Install with AltStore

1. Open **AltStore** on your iPhone (AltServer running on your Mac if needed).
2. **My Apps → +** (or share the `.ipa` → AltStore).
3. Pick the downloaded `MLB Edge.ipa`.
4. Trust the developer under **Settings → General → VPN & Device Management** if iOS asks.

Free Apple ID sideloads last **7 days**; reopen AltStore to refresh, or use a paid Apple Developer account for longer.

## If the build asks about distribution

Use profile **`altstore`** (`distribution: internal`). That produces a normal IPA AltStore can resign — you do **not** need App Store Connect.
