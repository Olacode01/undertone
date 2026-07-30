# Undertone — video script

~2:40. Read it a couple of times before recording, then talk it rather than
read it. Slight stumbles sound human; a perfectly read script sounds like a
perfectly read script.

Wake the site a minute before you start — the free tier sleeps.

---

### 0:00 — The problem  *(show your blue-suit photo)*

> This is me, in a royal blue suit. And I have no idea whether that colour
> actually suits me.
>
> Most people don't. You either guess, or you pay a stylist a few hundred pounds
> to look at your face and tell you.
>
> I built Undertone to answer it with measurements instead.

---

### 0:20 — Analyse  *(the live site, URL visible; upload the selfie)*

> It takes one selfie and sends it to YouCam's Facial Color Tones API, which
> gives back the exact colours of my skin, hair, eyes and eyebrows.

*(result lands)*

> And it puts me in Autumn.

---

### 0:40 — The honest bit  *(hover the warning box — slow down here)*

> But look at this first. The API told me my hair colour was a pale cream — it
> called it "Blonde". That's not my hair, that's the white background of the
> photo bleeding into the reading.
>
> Undertone caught that. It says so, it falls back to my eyebrow colour instead,
> and it lowers its own confidence to 0.65.
>
> I'd rather it tell me when it isn't sure than hand me a clean answer that's
> quietly wrong.

---

### 1:05 — The four axes  *(the four cards)*

> Underneath, it's measuring four things.
>
> My undertone is warm — that's a hue angle of 61 degrees, which is the
> direction my skin colour sits in, not how dark it is. That distinction matters,
> and I'll come back to it.
>
> My depth is deep. My contrast is low, because my skin and eyebrows are close in
> darkness. And my colouring is soft rather than vivid.
>
> Warm plus deep is Autumn.

---

### 1:30 — The palette  *(scroll to the swatches)*

> So here's what that means in practice. Rust, olive, clay, chocolate.
>
> My neutrals are cream rather than white. My metals are gold rather than silver.
> And it tells me to avoid icy pink, pastel blue — and pure black, because black
> is a maximum-contrast colour and my contrast is low.
>
> Every one of those follows from a number it measured.

---

### 1:55 — The ranking  *(scroll to the table)*

> Then it scores a garment catalogue against that palette, using CIEDE2000 —
> the colour difference standard, which accounts for how the eye actually
> perceives difference rather than just subtracting RGB values.
>
> Every verdict shows its working. This one's excellent because it's 10 units
> away from my rust.
>
> And down at the bottom — royal blue. Worst in the catalogue. 35 units from
> anything in my palette.
>
> Which is what I was wearing in the photo I started with.

---

### 2:20 — Try-on  *(click Try on for Croatia)*

> So let's test it. This one scored 76.

*(render appears)*

> That's YouCam's Apparel VTO. Same face, same photo — but now in a colour the
> analysis actually chose, for a reason I can point at.

---

### 2:40 — Close

> Two YouCam APIs — skin tone and virtual try-on — joined by colour science.
>
> Tone analysis on its own gives you numbers with nothing to do. Try-on on its
> own shows you clothes with no reason to pick them. Connected, they answer a
> question people genuinely can't answer for themselves.
>
> That's Undertone.

---

## Optional 15 seconds — only if you're under time

After the four axes, cut to `colour.py`:

> One thing worth showing. The obvious way to detect warm versus cool is to
> threshold the raw colour values. I did that first, and it read my skin as
> "neutral" — not because my undertone is ambiguous, but because those values
> shrink as skin gets darker.
>
> So it measures the hue angle instead, which is independent of lightness. Same
> face, and now it reads warm with high confidence.
>
> An analysis that only works on light skin isn't an analysis.

---

## Delivery notes

- **Pause after "And it puts me in Autumn."** Let it land.
- **Slow down on the warning box.** That's your credibility moment and it's the
  part most submissions won't have.
- **Point with the cursor** when you say a number. Judges follow the mouse.
- Record in sections and stitch in iMovie if a take goes wrong — much easier
  than nailing three minutes straight.
- Don't rush the close. Say the last line, wait a beat, then stop the recording.
