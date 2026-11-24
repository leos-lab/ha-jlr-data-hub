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

## Open the JLR data portal

1. Go to **[data.jlr.com](https://data.jlr.com/en_xi/index.html)**, JLR's data portal (currently in beta).
2. Choose **Access your data** → **Private**.
3. Sign in with your **JLR account**, the same one you use in the JLR app.
4. The first time, JLR asks a few questions to confirm your link to the car (you own it, lease it, or use its
   services). Answer them.
5. You land on **[My data](https://data.jlr.com/en_xi/my-data.html)**. The section you want is **Data Access
   Credentials** ("Set up and manage your Data access credentials").

## Create the credential

1. Under **Data Access Credentials**, **delete any credential you already have**. Only one is allowed per account.

    !!! warning
        If something else uses that credential (another app, or a jlr-server), it stops working.

2. Choose **Create Access Credential**, and fill it in:

    | Setting | Choose |
    |---|---|
    | Credential type | **Device-based** |
    | Vehicle | your car |
    | Data categories | **all of them** (Status, EV, Position, Journeys, and Attributes and Diagnostics if listed) |
    | Public certificate | upload `jlr.pem` |

3. Note the **client ID** the portal shows for the new credential.

## Set up live updates (recommended)

Without a stream, Home Assistant checks every 10 minutes. With one, changes come in as the car sends them.

1. In the portal, create a **stream configuration** and select **every signal** it offers.
2. Note its **username**. It's often the same as the client ID.
3. The **account ID** is the long ID in the stream's topic, `account/<account ID>/vehicles/…`. You can leave it out:
   Home Assistant reads it from JLR after you sign in.

[Next: connect Home Assistant :material-arrow-right:](connect.md){ .md-button .md-button--primary }
