# 2. Create your JLR credential

A "credential" (JLR also calls it a client) tells JLR which program may read which car. There's no password: you
prove who you are with a certificate whose private key never leaves Home Assistant.

## Get the certificate from Home Assistant

After choosing **Connect directly to JLR (recommended)**, Home Assistant makes a key pair and shows a certificate
like this:

```text
-----BEGIN CERTIFICATE-----
MIIDXTCCAhGgAwIBAgIU…
-----END CERTIFICATE-----
```

Copy all of it, including the `BEGIN` and `END` lines, into a text file called `jlr.pem`. Leave the Home Assistant
tab open: you'll come back to it.

## Create the credential in the portal

1. Sign in to the JLR Data Hub customer portal (linked from
   [developer.jlr.com](https://developer.jlr.com/docs/guides/personas/vehicle-owners)).
2. **Delete any credential you already have.** Only one is allowed per account.

    !!! warning
        If something else uses that credential (another app, or a jlr-server), it stops working.

3. Create a new credential:

    | Setting | Choose |
    |---|---|
    | Credential type | **Device-based** |
    | Vehicle | your car |
    | Data categories | **all of them** (Status, EV, Position, Journeys, and Attributes and Diagnostics if listed) |
    | Public certificate | upload `jlr.pem` |

4. Note the **client ID** the portal shows.

## Set up live updates (recommended)

Without a stream, Home Assistant checks every 10 minutes. With one, changes come in as the car sends them.

1. In the portal, create a **stream configuration** and select **every signal** it offers.
2. Note its **username**. It's often the same as the client ID.
3. The **account ID** is the long ID in the stream's topic, `account/<account ID>/vehicles/…`. You can leave it out:
   Home Assistant reads it from JLR after you sign in.

[Next: connect Home Assistant :material-arrow-right:](connect.md){ .md-button .md-button--primary }
