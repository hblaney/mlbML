# MLB Edge — iOS app

Expo app that wraps the live site (`https://mlb-edge-woad.vercel.app`) with a native tab bar:

**Board · Props · Moneyline · Watch · Accuracy**

## Run on a phone (Expo Go)

```bash
cd mobile
npm install
npm start
```

Scan the QR code with Camera (iOS) / Expo Go.

## Run on iOS Simulator

Needs **full Xcode** (not just Command Line Tools):

```bash
cd mobile
npm install
npx expo run:ios
```

## Build an installable IPA (AltStore / sideload)

```bash
cd mobile
npm install
npx eas-cli login
npm run build:ipa
```

Uses the `altstore` profile in `eas.json` (internal distribution).

## Notes

- Same live boards/pages as the website; the in-app WebView hides the site nav.
- Bundle id: `com.mlbedge.app`
- App Store submission needs an Apple Developer account + `eas submit`.
