# Devpost submission copy

Paste-ready. Each heading maps to a field on the submission form.

---

## Tagline

Your face decides your palette. Your palette decides what's worth trying on.

---

## Elevator pitch

Undertone measures the colour of your skin, hair and eyes, works out which
seasonal palette you belong to, scores a garment catalogue against that palette
using perceptual colour science, and shows you the best matches on your own
photo.

---

## Inspiration

I was looking at a photo of myself in a royal blue suit and realised I had no
idea whether it suited me. Nobody does. People buy clothes on instinct, or pay
a stylist a few hundred pounds for a colour analysis session that comes down to
one person's trained eye.

Two things struck me about the YouCam API. The Facial Color Tones analyzer
returns exact hex values for skin, hair, eyes, eyebrows and lips — the raw
inputs a stylist works from, but measured rather than judged. And Apparel VTO
can put a garment on you.

Between those two sits the actual question: *which* garment? That gap is where
the product is. Tone analysis alone gives you numbers with no action. Try-on
alone shows you clothes with no reason to pick them. Connected, they answer
something people genuinely can't answer for themselves.

---

## What it does

Upload a selfie. Undertone measures four axes:

- **Undertone** — warm or cool, from the CIELAB hue angle
- **Depth** — how light or deep, from L*
- **Contrast** — the lightness gap between skin and hair
- **Chroma** — how vivid or muted the natural colouring is

Those place you in a seasonal palette. Every garment in the catalogue is then
scored by its CIEDE2000 distance to the nearest palette colour, and every
verdict shows its working:

```
 1. Glitter Glam Gown   #ecddce   91.1  excellent  Almost exactly your Cream (ΔE 4)
 4. Croatia             #da0617   76.2  excellent  Almost exactly your Rust (ΔE 10)
16. Cloud Ruffle        #e4e4e4   36.6  clashes    ΔE 12 from an avoid-tone
20. France              #08369a   16.5  poor       Closest is Deep bark, ΔE 35
```

Then you try on the ones that scored well and see whether the maths was right.

In my case it ranked royal blue last — the colour I was wearing in the photo
that prompted the whole thing.

---

## How I built it

Python throughout. FastAPI backend, single-page frontend, no build step.

- **YouCam Facial Color Tones** for the raw colour measurements
- **YouCam Apparel VTO (`cloth-v3`)** for try-on
- **`colour.py`** — sRGB → CIELAB conversion, seasonal classification, palettes.
  Standard library only.
- **`match.py`** — CIEDE2000 implemented from the CIE specification. Standard
  library only.
- **`catalogue.py`** — builds a colour-matchable catalogue from YouCam's own
  garment templates by extracting the dominant garment colour from thumbnails.

The two colour-science modules have no third-party dependencies and no YouCam
coupling — they work on any hex input.

Deployed on Render. There's a demo mode that serves a cached profile and blocks
try-on, so the entire interface could be built and reviewed without spending
API units.

---

## Challenges I ran into

**My undertone detection was biased against deep skin.** The obvious approach is
to threshold the CIELAB a* and b* values. But those magnitudes scale with
lightness, so thresholds tuned on mid-light skin collapse toward zero on deep
skin — the reading returns "neutral" not because the undertone is ambiguous but
because the sample is darker. My own face scored +0.04, effectively a shrug.

The fix was to use the hue *angle*, `atan2(b*, a*)`, which measures the direction
of the colour rather than its magnitude and is therefore lightness-invariant. The
same face then read "warm, 61°", and deep skin with black hair classified at 0.94
confidence instead of 0.54.

On an API whose stated purpose includes working across ethnicities, shipping an
analysis layer calibrated only for light skin would have undercut the whole
thing.

**The API returned a confident wrong answer.** On a passport photo it reported
`hair_color: #FAF0BE`, labelled "Blonde" — pale cream, on deep brown skin. It was
sampling the white backdrop. That fed a fictitious skin-to-hair contrast of
ΔL* 62 and pushed the classification into the wrong season.

Rather than trust the detector, Undertone now validates it: if hair comes back
very light and desaturated, it says so in the interface and falls back to
eyebrow colour, which tracks hair depth and sits inside the face region where the
background can't reach. Stated confidence drops accordingly. Contrast went from
a fictitious 62 to a real 4.5.

**Automatic garment colour extraction produced a beautiful lie.** My first
version cropped a fixed band from each thumbnail and took the dominant colour.
Every garment scored "excellent" — because the crop was landing on the models'
skin, and warm skin tones match a warm palette. A matcher that flatters every
input is broken, and "everything scored excellent" was the tell.

I tried learning each model's skin from the face band and subtracting it, which
helped, but garment layouts vary too much for one fixed crop. I stopped there:
20 garments is a ten-minute hand-label, real retail integrations read colour
from product metadata anyway, and the extractor stays in the repo as the path
to scale with its limitation documented.

**`template_id` is documented but rejected.** The AI Clothes guide lists
`ref_file_id`, `ref_file_url` or `template_id` as garment sources. Both `cloth`
and `cloth-v3` reject any payload carrying `template_id`, and the error points
somewhere else entirely — `InvalidParameters: missing required properties
(["src_file_url"])`, a `oneOf` failure listing every branch it didn't match. The
workaround is to use the template's thumbnail URL as `ref_file_url`.

---

## Accomplishments I'm proud of

The colour analysis works across the tonal range rather than on light skin
alone, and I can show the before-and-after numbers that prove it.

Every recommendation is falsifiable. There's no "this suits you" without a ΔE
attached, which means a user can disagree with the system on specific grounds
rather than vibes.

The system tells you when it doesn't trust its own input. That was the hardest
thing to be disciplined about — it's tempting to hide a bad reading and show a
clean result.

The whole thing cost single-digit API units to build, because everything except
the measurements themselves runs on cached data.

---

## What I learned

Perceptual colour distance is not optional. Euclidean RGB treats a 20-point shift
in dark navy as equal to 20 points in bright yellow; the eye does not. CIEDE2000
exists precisely because "how different do these look" is not "how far apart are
these numbers".

A metric that flatters every input is broken. Twice during this build I got
results that looked great and meant nothing. Both times the tell was the same:
no discrimination. Everything scoring well is a bug report.

And validating your inputs matters more than polishing your outputs. The most
useful thing in the interface is the warning box that admits a measurement was
unreliable.

---

## What's next

- The twelve-season model rather than four, which refines chroma and depth
  within each season
- Read garment colour from product metadata, so it works against a real retail
  catalogue rather than 20 hand-labelled items
- Add YouCam Skin Analysis on the `raw_score` axis to track skin condition over
  time. The docs are explicit that `ui_score` is adjusted upward because
  "consumers generally prefer positive evaluations" — which makes it useless for
  measuring change, and most integrations will reach for it by default
- Save profiles so returning users skip straight to the catalogue

---

## Features, functionality, and retail value

*(For the Devpost field asking specifically about consumer/retail value.)*

### What it does

Undertone turns a single selfie into a personal colour palette, then uses that
palette to decide which garments are worth showing you — and puts the best ones
on your own photo.

**Features**

- **Seasonal colour analysis from one photo.** Measures undertone, depth,
  skin-to-hair contrast and chroma from the hex values returned by YouCam's
  Facial Color Tones API, and places the user in a seasonal palette.
- **Explained results, not verdicts.** Every classification shows the
  measurement behind it — undertone as a CIELAB hue angle, depth as L*, contrast
  as ΔL* — in plain language alongside the number.
- **Input validation with honest confidence.** When the underlying detection is
  unreliable (for example, a pale background read as hair colour), the app says
  so, falls back to a more robust feature, and lowers its stated confidence
  rather than presenting a clean but wrong answer.
- **Garment ranking with a justification.** Each item is scored by CIEDE2000
  distance to the nearest palette colour, and every verdict carries its ΔE.
- **Virtual try-on on the recommended items.** The user sees the top matches on
  their own photo via YouCam Apparel VTO.
- **A palette that translates to shopping decisions** — colours to wear, base
  neutrals, colours to avoid, and which metals suit.

**How it works**

1. Selfie → YouCam Facial Color Tones API → hex values for skin, hair, eyes,
   eyebrows, lips
2. Those convert to CIELAB and resolve into four measured axes → seasonal palette
3. The garment catalogue is scored by CIEDE2000 against that palette
4. Top matches → YouCam Apparel VTO → rendered on the user's photo

### Consumer value

Choosing clothes by colour is guesswork for almost everyone. The alternative is
a professional colour analysis session, which costs money, requires an
appointment, and comes down to one person's trained eye. Undertone gives the
same output in about a minute, for free, with the reasoning shown.

The practical payoff isn't the season label — it's the shopping rules that fall
out of it. Cream rather than optic white. Gold rather than silver. Charcoal
rather than pure black. Those are decisions people make repeatedly and
expensively, usually without any basis.

### Retail value

**It answers the question virtual try-on doesn't.** VTO shows a shopper how a
garment fits and drapes. It doesn't tell them whether the colour works for them
— and colour is the attribute shoppers are least equipped to judge from a
product page. Undertone adds the *should I* to VTO's *what would it look like*,
which makes an existing VTO deployment more useful without new photography or
new inventory data.

**It narrows an overwhelming catalogue to a defensible shortlist.** A retailer
showing 400 items in a category can rank them per-shopper by measured colour fit.
That's personalisation derived from the shopper's own appearance rather than
from purchase history — so it works on the first visit, before any behavioural
data exists, which is exactly where recommendation systems are weakest.

**It targets colour-driven returns.** "It didn't look right on me" is a return
reason that fit-focused tools can't address, and returns are a structural cost
in online apparel. A colour-fit score shown before purchase gives the shopper a
reason to choose differently, and gives the retailer a signal to merchandise on.

**It integrates against data retailers already hold.** Matching needs one hex
value per product. Retailers already carry colour metadata in their PIM, so
there's no image pipeline to build — the same reason this approach scales past a
demo catalogue.

**It builds trust rather than spending it.** Because every recommendation shows
its ΔE and the app flags its own low-confidence readings, shoppers can disagree
with it on specific grounds. A recommender that admits uncertainty is one people
keep using; one that flatters every input gets ignored after the first bad
purchase.

**It works across skin tones.** The analysis uses lightness-invariant hue angle
rather than raw CIELAB magnitudes, so classification holds across the tonal
range. For any retailer serving a diverse customer base, a colour tool that only
performs on light skin is not deployable.

---

## Built with

`python` `fastapi` `youcam-api` `perfectcorp` `cielab` `ciede2000` `colour-science`
`uvicorn` `pillow` `httpx` `render`

---

## Describe your contribution

Solo project. I designed, built, deployed and documented all of it.

It's worth being precise about the boundary between what the YouCam API provides
and what I wrote, because the value of this project sits entirely in the gap
between them.

**What YouCam provides:** hex colour measurements of a face, and a rendering
engine that puts a garment on a photo.

**What I built:** everything that turns the first into a reason to invoke the
second.

- **`colour.py`** — sRGB → linear RGB → XYZ → CIELAB conversion, and a seasonal
  classifier built on four measured axes: undertone from the lightness-invariant
  hue angle, depth from L*, skin-to-hair contrast from ΔL*, and chroma from
  feature saturation. Includes the seasonal palettes and the plain-language
  explanation generated from the measurements. Standard library only.
- **Input validation and graceful degradation** — detecting when the API's hair
  reading is actually the photo background, falling back to `eyebrow_color`,
  and lowering stated confidence to match. This is the part I'd point at first.
- **`match.py`** — CIEDE2000 implemented from the CIE specification, plus the
  garment scoring model: fit distance to the nearest palette colour, clash
  distance to the nearest avoid-tone, and a verdict with its ΔE attached.
  Standard library only.
- **`youcam_client.py`** — async driver for the API. Handles the presigned
  upload the docs warn about, mandatory polling, and a persistent unit budget
  that charges only successful tasks.
- **`catalogue.py`** — builds a colour-matchable catalogue from YouCam's own
  garment templates, including per-image skin subtraction so the model's face
  isn't mistaken for the garment.
- **`server.py` and the frontend** — FastAPI backend and a single-page interface
  designed to show the reasoning rather than just the verdict, including a demo
  mode that serves cached results so the UI could be built without spending
  units.
- **Deployment, README, and the API integration notes** documenting the
  undocumented behaviour I hit.

The two colour-science modules have no third-party dependencies and no YouCam
coupling. They operate on hex values from any source, and are reusable for any
colour-analysis work.

The total API spend across the whole build was single-digit units, because
everything except the measurements themselves runs on cached data.

---

## Optional questions

### Was there a moment where the API surprised you — good or frustrating?

Both, and the good one mattered more.

**The good surprise: `eyebrow_color`.** I went in thinking the Facial Color Tones
API was a skin tone endpoint. It also returns eyebrow, lip and eye colour, and I
initially treated those as padding. Then the hair detection failed on my passport
photo — it read the white backdrop and reported my hair as pale cream, labelled
"Blonde", on deep brown skin. That wrecked the skin-to-hair contrast axis.

`eyebrow_color` turned out to be the fix. Eyebrows track hair depth closely and
sit inside the face region, where a background can't leak in. An unglamorous
field I nearly ignored ended up being the thing that made the analysis robust.
It's worth surfacing in the docs as a reliability feature, not just extra data.

**The good surprise, part two: the confidence block on other endpoints.** The
structured outcome with a confidence score and specific evidence strings is
genuinely well designed and barely documented. It's the feature that makes
results safe to act on automatically, because it tells you when not to.

**The frustrating one: `template_id`.** The AI Clothes guide lists
`ref_file_id`, `ref_file_url` or `template_id` as garment sources, and there's a
templates endpoint that returns `template_id` values. Neither `cloth` nor
`cloth-v3` accepts a payload containing one. Worse, the error points somewhere
unrelated — `InvalidParameters: missing required properties (["src_file_url"])`,
which is a `oneOf` failure enumerating every branch it didn't match. I spent
real time checking my source image before realising the source image was fine.

The workaround is to use the template's `thumb` URL as `ref_file_url`, which
works well. But a documented parameter that the API rejects, with an error
naming a different field, is the single highest-value fix available in the
developer experience.

**One more worth flagging:** the File API hands back a presigned S3 URL, and if
your HTTP client has a default `Authorization: Bearer` header, S3 rejects the
upload with `Only one auth mechanism allowed`. That's correct behaviour — and it
also means the naive implementation sends your YouCam API key to a third party.
Worth an explicit warning in the quickstart.

---

### Are there industries or use cases Perfect Corp's API could serve that nobody is talking about yet?

**Prosthetics and medical device colour matching.** Matching a prosthetic cover,
silicone restoration or orthotic to a patient's skin tone is currently done by
eye, often against a physical shade guide, and it's notoriously poor for deep
skin tones. A patient-specific measurement in CIELAB, taken from a phone, would
give technicians a numeric target instead of a judgement call. The gap between a
prosthesis that matches and one that doesn't is not cosmetic to the person
wearing it.

**Uniform and workwear specification.** Airlines, hospitality groups, schools
and health services choose one uniform palette for a workforce spanning the
entire tonal range, and they choose it on a mood board. Aggregate tone analysis
across a real staff population would let a designer test a proposed palette
against the people who'll actually wear it — and identify colours that work
badly for a meaningful share of them before committing to a production run.

**Catalogue imagery QA.** Retailers shoot the same garment across multiple
sessions, studios and models, and skin tones drift between shoots. Running tone
analysis across a product catalogue would surface inconsistent colour rendering
— which matters commercially, because a shopper comparing two images can't tell
whether the difference is the garment or the lighting. This is a colour-science
problem retailers currently solve manually, if at all.

**A shared thread:** all three want *measurement*, not beautification. The API is
positioned around consumer beauty experiences, but the underlying capability is
a calibrated colour measurement of a human being taken from a phone camera. That
is useful anywhere a decision currently rests on someone's eye and a physical
swatch book.

---

### Where did you hit a wall technically? How did you work around it?

**The wall: extracting garment colour from thumbnails.**

The template catalogue gives you `id`, `title` and a thumbnail URL — no colour.
Colour is what my entire matching layer runs on, so I had to derive it from the
image.

First attempt: crop a band from the middle of the thumbnail, quantise, take the
dominant colour. Every single garment came back scoring "excellent" against my
palette. That looked like success and was actually the bug — the crop was
landing on the models' skin, and warm skin tones match a warm palette. I was
matching myself against other people's faces. The tell was that nothing
discriminated: a matcher that flatters every input is broken.

Second attempt, and I still think this idea is right: learn each model's skin
colour from the face band of their own thumbnail, then exclude any torso cluster
within ΔE 16 of it. Per-image rather than a global "skin tone range", because a
global rule would also exclude rust, clay and camel — the exact colours an Autumn
palette wants. That worked for some layouts. But the sports thumbnails frame the
jersey high, so my "face band" started sampling the shirt, and the two columns
inverted.

**The workaround was knowing when to stop.** Layouts varied too much for any
fixed crop, and I'd spent two iterations on it. Twenty garments is a ten-minute
hand-label. Real retail integrations read colour from product metadata anyway —
nobody parses pixels for this in production. So I hand-verified the twenty,
documented the limitation in the README, and kept the extractor in the repo as
the path to scale with its weakness stated honestly.

I also added a `--debug` flag that writes the sampled crops to disk. Looking at
what the code is actually measuring is faster than reasoning about why a number
looks wrong, and I should have built it before the first attempt rather than
after the second.

**The other wall, with a better ending: my undertone detection was biased against
deep skin.** I thresholded raw CIELAB a* and b* values. Those magnitudes scale
with lightness, so the reading collapses toward zero on darker skin — my own face
scored +0.04, a shrug, not because my undertone is ambiguous but because the
sample was dark. Switching to the hue angle `atan2(b*, a*)`, which measures
direction rather than magnitude and is therefore lightness-invariant, fixed it:
the same face read "warm, 61°", and deep skin with black hair went from 0.54 to
0.94 confidence. That one's worth flagging to anyone building on this API, since
the naive approach is the obvious one and it fails quietly.

---

## Try it out

- Live demo: https://undertone-55a9.onrender.com
- Source: https://github.com/Olacode01/undertone

> The demo is on a free tier that sleeps when idle — the first request can take
> up to 50 seconds to wake.
