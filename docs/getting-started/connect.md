# 3. Connect Home Assistant

## Directly to JLR

Back in Home Assistant, on the same setup screen as the certificate:

1. Enter the **Client ID** and your **VIN**.
2. Enter the **Stream username** if you set up a stream. The **Stream account ID** is optional.
3. Choose **Submit**. Home Assistant shows a link and a short code.
4. Open the link, sign in with your **JLR account** (the one you use in the JLR app), and approve the code.
5. Setup finishes by itself. You get one device for the car, with its [entities](../using/entities.md).

!!! success "You're done"
    The sign-in renews itself as long as Home Assistant is running. If it ever lapses, Home Assistant shows a
    **Reconfigure** notice: sign in again with the same credential, with no portal changes.

??? question "\"JLR refused the sign-in. Check the client ID.\""
    The client ID doesn't match a credential with this certificate. Check you uploaded the certificate from *this*
    setup, not an earlier one: each attempt makes a new key. If in doubt, close the setup, start again, and replace
    the portal credential with the new certificate.

### Options

Settings → Devices & services → JLR Data Hub → **Configure**: change the stream username or account ID.

## Through jlr-server

!!! abstract "Advanced"
    Only if you run [jlr-server](../advanced/jlr-server.md), which then holds the JLR credential instead of Home
    Assistant.

1. Choose **Read from a jlr-server (advanced)**.
2. **Server address**: the full address with `http` or `https`, for example `http://192.168.1.10:9293` or
   `https://jlr.example.com`.
3. **API token**: the server's `API_TOKEN`.

Home Assistant checks the server holds a credential for a car, then adds it. Options: how often to read the server
(30–300 seconds, 60 by default). If the server's token changes, Home Assistant asks for the new one.

[Next: your entities :material-arrow-right:](../using/entities.md){ .md-button .md-button--primary }
