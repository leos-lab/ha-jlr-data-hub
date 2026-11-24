# Before you start

- [ ] **A connected car.** A Jaguar or Land Rover with an active connected-services subscription (InControl or JLR
      Remote). If the JLR app shows your car's battery and location, it's connected.
- [ ] **You're the primary user.** The Data Hub only lists cars where your JLR account is the primary user.
- [ ] **Your JLR account**, the one you use in the JLR app. It's also your login for JLR's data portal,
      [data.jlr.com](https://data.jlr.com/en_xi/index.html) (**Access your data** → **Private**). There's nothing else to
      sign up for.
- [ ] **Home Assistant 2026.2 or newer**, with [HACS](https://hacs.xyz) to install from. You can also copy the files in
      by hand.
- [ ] **Your VIN**, the 17-character vehicle identification number. It's in the JLR app, on your V5C (logbook), and at
      the bottom of the windscreen.

## Where it works

JLR's data portal covers JLR vehicles first sold in the **EU** (under the EU Data Act) and, on a goodwill basis, the
**UK**. This integration was built and tested on a UK I-Pace. The portal is still in beta: if it doesn't list your
car, it isn't available for that car or account yet.

## One credential per account

JLR lets each account have **one** Data Hub credential at a time. To make a new one, you delete the old one first. So:

- Whatever holds the credential is the only thing that can read the car from JLR.
- If you already made a credential for something else (another app, a script), this integration replaces it.
- To use the car's data in several places, see [jlr-server](../advanced/jlr-server.md).

[Next: install the integration :material-arrow-right:](install.md){ .md-button .md-button--primary }
