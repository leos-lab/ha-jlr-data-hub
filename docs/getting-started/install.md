# 1. Install the integration

=== "HACS (recommended)"

    1. In Home Assistant, open **HACS**.
    2. Open the **⋮** menu (top right) → **Custom repositories**.
    3. Paste `https://github.com/leos-lab/ha-jlr-data-hub`, choose type **Integration**, then **Add**.
    4. Search HACS for **JLR Data Hub**, open it and choose **Download**.
    5. **Restart Home Assistant**: Settings → System → ⏻ → **Restart Home Assistant**.

=== "By hand"

    1. Download the [latest code](https://github.com/leos-lab/ha-jlr-data-hub/archive/refs/heads/main.zip).
    2. Copy its `custom_components/jlr_data_hub` folder into your Home Assistant `config/custom_components/` folder,
       so you have `config/custom_components/jlr_data_hub/manifest.json`.
    3. Restart Home Assistant.

!!! note "Why the restart?"
    Home Assistant only finds new integrations when it starts. Until you restart, **JLR Data Hub** won't appear in the
    list of integrations to add.

## Start the setup

Settings → **Devices & services** → **Add integration** → search for **JLR Data Hub**.

You're asked how to connect:

- **Connect directly to JLR (recommended)**: Home Assistant holds the credential. Continue to
  [create your JLR credential](jlr-credential.md).
- **Read from a jlr-server (advanced)**: only if you [run a jlr-server](../advanced/jlr-server.md). Skip to
  [connect Home Assistant](connect.md#through-jlr-server).

[Next: create your JLR credential :material-arrow-right:](jlr-credential.md){ .md-button .md-button--primary }
