# Troubleshooting

??? failure "JLR Data Hub isn't in the list of integrations"
    Restart Home Assistant after installing. Check `config/custom_components/jlr_data_hub/manifest.json` exists. Then
    clear your browser cache, or try the Home Assistant app.

??? failure "\"JLR refused the sign-in. Check the client ID.\""
    - The client ID has a typo, or it belongs to a credential made with a different certificate. Each setup attempt
      makes a **new** key, so the certificate in the portal must come from this attempt.
    - Start the setup again, then replace the portal credential with the new certificate.

??? failure "Sign-in didn't finish"
    The code expired (about 15 minutes) or was declined. Start the setup again.

??? warning "Values are out of date (the lock, say)"
    That's usually the car, not the integration: it reports when switched off, while charging and on some events, and
    some changes take minutes to reach JLR. Check **Last reported**. See [How fresh is the data?](../using/freshness.md)

??? warning "Stream: dropped or waiting"
    JLR's broker drops connections now and then, and its streaming passwords only last about 5 minutes. The
    integration reconnects by itself, backing off after repeated failures. If it stays down:

    - Check the **stream username** in the integration's options matches the portal's stream configuration.
    - Check the stream configuration in the portal still exists and has signals selected.
    - Polling still works meanwhile, every 10 minutes.

??? warning "Some entities are unavailable"
    The car hasn't sent that value, or sends `-1` ("not set"). Charge limit and Time to full are often unavailable
    when not charging. Petrol-only and diesel-only values don't apply to electric cars.

??? failure "Home Assistant asks me to sign in again"
    The JLR sign-in lapsed, for example after Home Assistant was off for a long time. Choose **Reconfigure** and
    approve the new code. The portal credential stays the same.

??? failure "It stopped working after I set up something else with JLR"
    Only one credential is allowed per account. If you created a credential for another program, the old one (and so
    this integration) stopped working. Use [jlr-server](../advanced/jlr-server.md) to share one credential.

## Diagnostics

Settings → Devices & services → JLR Data Hub → ⋮ → **Download diagnostics**. Tokens, your VIN, client ID and the car's positions are removed.
Attach the file when you [report a problem](https://github.com/leos-lab/ha-jlr-data-hub/issues).
