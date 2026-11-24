# Before you start

- [ ] **A connected car.** A Jaguar or Land Rover with an active connected-services subscription (InControl or JLR
      Remote). If the JLR app shows your car's battery and location, it's connected.
- [ ] **You're the primary user.** The Data Hub only lists cars where your JLR account is the primary user.
- [ ] **A JLR Data Hub account.** Sign in to the portal with the same JLR account you use in the JLR app. There's a
      link from [developer.jlr.com](https://developer.jlr.com/docs/guides/personas/vehicle-owners).
- [ ] **Home Assistant 2026.2 or newer**, with [HACS](https://hacs.xyz) to install from. You can also copy the files in
      by hand.
- [ ] **Your VIN**, the 17-character vehicle identification number. It's in the JLR app, on your V5C (logbook), and at
      the bottom of the windscreen.

## Where it works

The Data Hub was set up for the EU Data Act. It also works for UK cars: it was built and tested on a UK I-Pace. If the
portal doesn't list your car, it isn't available for that car or account yet.

## One credential per account

JLR lets each account have **one** Data Hub credential at a time. To make a new one, you delete the old one first. So:

- Whatever holds the credential is the only thing that can read the car from JLR.
- If you already made a credential for something else (another app, a script), this integration replaces it.
- To use the car's data in several places, see [jlr-server](../advanced/jlr-server.md).

[Next: install the integration :material-arrow-right:](install.md){ .md-button .md-button--primary }
