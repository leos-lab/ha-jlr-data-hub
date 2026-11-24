# FAQ

**Can it lock the car, start climate or charging?**
: No. The JLR Data Hub is read-only, so nothing using it can control the car.

**Does it use my JLR app login?**
: You sign in with your JLR account once, on JLR's own page, to approve access. Home Assistant never sees your
  password. It gets a token tied to its own key.

**Does it cost anything?**
: The Data Hub is free for owners. You need an active connected-services subscription for the car to report.

**Which cars work?**
: Jaguar and Land Rover cars with connected services that the Data Hub lists for your account. Built on a UK 2020
  Jaguar I-Pace. Electric-only values (battery, charging) only apply to EVs and plug-in hybrids.

**Why can't I see past trips' battery use?**
: JLR doesn't record it. Only [jlr-server](../advanced/jlr-server.md) works it out, from reports it saw itself, so it
  starts from when you set it up.

**Can I use the same credential in two places?**
: Not directly: JLR allows one credential per account, and it's tied to one key. Use
  [jlr-server](../advanced/jlr-server.md) as a proxy.

**What about my old warnings or fault history?**
: The Data Hub doesn't keep a history of warnings. A dealer can read stored fault codes from the car, or you can ask
  JLR for your data under data protection law.

**Is this made by JLR?**
: No. It's an independent open-source project, not affiliated with or endorsed by Jaguar Land Rover.
