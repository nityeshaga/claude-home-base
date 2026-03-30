# Creative Direction: Cora

**Product:** AI email assistant that screens, drafts, and briefs your inbox
**Built by:** Every × darkroom.engineering

---

## The Vision

Cora takes care of your email. It reads everything that comes in, decides what actually needs your attention, drafts responses that sound like you wrote them, and summarizes the rest into a brief you can scan in two minutes. The inbox stops being a place you dread and becomes something you glance at — handled, organized, calm.

But here's the thing about email: nobody talks about it the way they talk about other broken things in their life. Nobody says "I hate email" with the same energy they'd say "I hate my commute." They say it with a sigh. With resignation. Email isn't an enemy — it's a slow suffocation. It's the feeling of knowing there are 47 unread messages waiting for you, most of which don't matter, but you can't be sure which ones do, so you have to wade through all of them. It's background anxiety. It's the reason people check their phone at dinner.

This is why Cora can't look like a productivity tool. It can't look like Superhuman or Shortwave or Spark — tools that make email *faster*, that celebrate keyboard shortcuts and zero-inbox streaks and throughput. Those tools accept the premise that email is work and try to help you do the work more efficiently. Cora rejects the premise. Email shouldn't feel like work. It should feel like something that's taken care of. The way a good assistant handles your schedule — you don't manage your calendar more efficiently, you just stop thinking about it.

So the entire creative direction flows from one word: **breath**.

Not speed. Not efficiency. Not power. Breath. The feeling of stepping outside on a perfect morning after being in a stuffy room. The moment your chest opens and you realize you'd been holding tension you weren't even aware of. That's what Cora does to your relationship with email. And the website needs to make you feel that sensation before you understand any of the product features.

When someone arrives at cora.computer, the first thing they should experience is space. Openness. Sky. Before they read a single word, the visual environment should feel like the opposite of an inbox — expansive where email is cramped, quiet where email is noisy, beautiful where email is utilitarian. The design itself should be the first exhale.

Then, as they move through the experience, they should encounter the product naturally — not as a feature list, but as moments in a landscape. They learn that Cora screens their email the way they'd learn there's a river at the bottom of a valley: by arriving there. They discover the drafting capability the way they'd notice a beautiful house in the distance: it appears in the environment and invites them closer. The brief feature should feel like reaching a clearing — suddenly everything is visible and organized, and you can see the whole picture at once.

By the time they reach the end, the visitor should feel something that no email tool has ever made them feel: desire. Not "I should sign up because this looks useful." But "I want my inbox to feel like *that.*" The design should create a destination so appealing that signing up is less about the features and more about wanting to live in the world that Cora creates. The CTA shouldn't feel like a conversion. It should feel like an invitation.

This is where the beauty matters strategically, not just aesthetically. Cora asks for access to your inbox — one of the most personal digital spaces a person has. Every email you've sent, every awkward reply, every neglected thread. Trusting a product with that access requires more than a feature comparison and a security badge. It requires the feeling that the people who built this care about beautiful things, and will treat your private space with the same care they put into their public one. The design IS the trust signal.

The competitors don't think this way. Superhuman leads with speed — "the fastest email experience ever made." Shortwave leads with AI — "AI-powered email for teams." Spark leads with features — "smart inbox, email scheduling, send later." They all compete on the dashboard. They all show UI screenshots and keyboard shortcut tables and comparison matrices. Cora should compete on none of this. Cora should compete on feeling. When someone asks "why Cora instead of Superhuman?" the answer isn't a feature list. It's "go look at their website and tell me which one you'd rather live with."

The landing page needs to communicate three things, but it should communicate them the way a great film communicates its themes — through experience, not exposition. First, Cora reads your email so you don't have to (it screens). Second, Cora writes like you (it drafts in your voice). Third, Cora gives you the highlights (it briefs). These three truths should be discovered as moments in a journey, not read as bullets on a page.

And critically, the product itself needs to carry the same atmosphere. Lucas Crespo designed the oil-painted sky backgrounds for the Cora *app*, not just the marketing page. When you open Cora to check your email, you should feel the same breath of fresh air as when you visited the website. The landing page isn't a promise the product fails to keep. It's a preview of the actual daily experience.

If someone remembers one thing about Cora, it should be the feeling of scrolling from sky to earth — descending through painted clouds into a golden prairie. Twelve seconds of scroll that do more storytelling than a thousand words of copy. That transition IS the brand: from overwhelm to peace, from chaos to calm, from holding your breath to breathing freely.

---

## How We Achieve This

### Typography

The headline font is Signifier by Klim Type Foundry — a transitional serif with sharp, high-contrast strokes that carries literary, almost philosophical weight. This is a $300+ premium typeface. When you read "Give Cora your inbox. Take back your life." in Signifier, it reads like the opening line of an essay, not a marketing headline.

The hero H1 uses Signifier at weight 300 (Light), 55px. Light weight at display size is almost unheard of in SaaS — most sites scream with bold headlines. Cora whispers. The delicacy mirrors the lightness the product promises for your inbox.

"Briefed" appears in Signifier Italic — calligraphic, personal, like a handwritten label in a notebook.

Body copy, navigation, buttons use Switzer, a geometric neo-grotesque sans-serif. Clean and modern for the practical communication while Signifier handles the emotional communication.

- Hero: Signifier 55px / weight 300 / line-height 1.18
- Section heads: Signifier 36-45px / weight 400
- Feature titles: Signifier 24-34px / weight 400
- Body: Switzer 18px / weight 400 / line-height 1.24
- CTAs: Switzer 14px / weight 400
- Nav: Switzer 20px / weight 400
- Fallback stack prioritizes serifs: `Switzer, Signifier, "Hoefler Text", "Baskerville Old Face", Garamond` — the editorial DNA runs all the way down

### Color

The entire experience is bathed in sky blue — not cold corporate blue, but warm, atmospheric, alive. White is the only text color, at varying opacities. You're not looking AT blue. You're INSIDE it.

- Primary blue: #117BC8 / rgb(17, 123, 200)
- Deeper blue: #0B57D0
- Dark accent: #065BA3
- Mid-tone: #488FCB
- Whisper blue: #F2F6FC
- Frosted nav: rgba(255, 255, 255, 0.898)
- Footer black: #000000
- Red accent: rgb(207, 55, 45) for email importance markers
- The transition from blue to gold happens through the oil painting itself — no CSS section break, no divider. The painting's sky gives way to trees, gives way to golden fields. Color shift IS the narrative.

### The Oil Painting

A single continuous digital oil painting (`background.webp`) spans the entire 12,306px page, transitioning from blue sky with cumulus clouds to golden wheat fields with distant mountains. Style evokes American Hudson River School — Thomas Cole, Albert Bierstadt. Visible brushwork, romantic grandeur, atmospheric depth. Deliberately not photorealistic.

- `background.webp` — the main painting
- `cloud.webp` — separate parallax cloud layer
- `sides.webp` — tree/foliage framing at edges
- Multiple z-planes create genuine spatial volume — background, midground clouds, foreground UI

### Physical Metaphors

Every UI element reinforces: email is physical mail.

- The envelope opens via scroll-linked animation, email cards burst out as individual PNGs (emails/1-6.png), then the envelope closes and seals with a "MADE BY EVERY" postal stamp
- Email inbox rows appear as separate images (rows/1-7.png) sliding in like mail sorted on a table
- The Brief feature fans out like playing cards
- The stamp in the footer is a maker's mark pressed into wax
- The Cora logo: lowercase "cora" in a rounded sans-serif inside a white rounded-rectangle border — small, understated, like a name embossed on a leather notebook

### Spatial Composition

No visible page boundaries. No max-width containers. No grid lines. Elements float freely in the landscape.

- Content widths are narrower than typical SaaS: 357px (mobile), 678-792px (desktop) — a focused, intimate tunnel through the vast painting
- Section spacing: 108px+ between sections
- Border radii universally generous: 9999px (pills), 25px, 20px, 12px — no sharp corners anywhere
- Navigation minimal: just "Log in" and "Start free trial" in the corner. No hamburger menu, no Features/Pricing/About tabs. The page IS the navigation.

### Motion

Motion feels like wind. Nothing snaps or bounces. Everything drifts, floats, settles.

- Lenis smooth scrolling provides inertia-based, Apple-like momentum
- All animations are scroll-linked, not time-based — they respond to the visitor's pace
- Parallax layers: background painting (slowest), cloud layer (medium), UI elements (fastest)
- Testimonial carousel: gentle horizontal auto-scroll, content duplicated in DOM for seamless loop
- Envelope state change: two images (open/closed) transitioned via scroll position
