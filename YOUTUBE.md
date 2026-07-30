# YouTube listing

## Title

Undertone — AI colour analysis that knows what you should wear | YouCam API Hackathon

*(Alternatives if you want shorter)*

- Undertone — I measured my own colouring to find out what suits me
- Undertone — AI seasonal colour analysis + virtual try-on

---

## Description

Your face decides your palette. Your palette decides what's worth trying on.

Undertone measures the colour of your skin, hair and eyes, works out which
seasonal palette you belong to, scores a garment catalogue against it using
perceptual colour science, and shows you the best matches on your own photo.

I started with a photo of myself in a royal blue suit, with no idea whether the
colour suited me. Undertone ranked that blue last out of everything in the
catalogue — 35 ΔE units from anything in my palette.

🔗 Live demo: https://undertone-55a9.onrender.com
💻 Source: https://github.com/Olacode01/undertone

(The demo runs on a free tier that sleeps when idle — the first load can take up
to 50 seconds.)

━━━━━━━━━━━━━━━━━━━━━━

WHAT IT DOES

Upload a selfie. It measures four things:

• Undertone — warm or cool, from the CIELAB hue angle
• Depth — how light or deep, from L*
• Contrast — the lightness gap between skin and hair
• Chroma — vivid or muted

Those place you in a seasonal palette. Every garment is then scored by its
CIEDE2000 distance to the nearest palette colour, so every recommendation
carries a number you can argue with. Then you try the good ones on.

━━━━━━━━━━━━━━━━━━━━━━

TWO THINGS I'D CALL OUT

It tells you when it doesn't trust its own input. On my passport photo the API
reported my hair as pale cream and labelled it "Blonde" — it was reading the
white background. Undertone detects that, says so, falls back to eyebrow colour,
and lowers its stated confidence.

The colour analysis works across skin tones. My first version thresholded raw
CIELAB a*/b* values, which shrink as skin gets darker — so it read deep skin as
"neutral" regardless of the actual undertone. Switching to the hue angle, which
is independent of lightness, fixed it. On an API built for use across
ethnicities, that wasn't optional.

━━━━━━━━━━━━━━━━━━━━━━

BUILT WITH

Python · FastAPI · YouCam Facial Color Tones API · YouCam Apparel VTO ·
CIELAB · CIEDE2000 · Render

The colour science modules have no third-party dependencies — sRGB→CIELAB
conversion, seasonal classification and CIEDE2000 are implemented from the CIE
specification in plain Python.

━━━━━━━━━━━━━━━━━━━━━━

Built for the YouCam AI Hackathon, Skin AI + Apparel VTO combined track.

#YouCamAPI #PerfectCorp #Hackathon #ColourAnalysis #VirtualTryOn #Python
#FastAPI #ComputerVision #ColorScience

---

## Chapters

Adjust the timestamps to your actual recording, then paste into the description.
YouTube turns them into clickable chapters automatically — the first one must be
0:00.

```
0:00 The problem
0:20 Analysing a selfie
0:40 When the API gets it wrong
1:05 The four measurements
1:30 Your palette
1:55 Ranking the catalogue
2:20 Virtual try-on
2:40 Why both APIs together
```

---

## Thumbnail

The before/after pair works best — blue suit on the left, try-on result on the
right. Failing that, the colour profile card with the warning box visible.
