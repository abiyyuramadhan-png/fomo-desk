# Put the desk on a server (iPhone)

PAPER only. The desk does not hold a wallet and does not send real trades. Never type a FOMO password or a wallet key.

Prices checked 8 Nov 2026 on the providers' own pages. The checkout screen is the price that matters. Tax and paid add-ons cost extra.

## 1. Create the server

Use Safari. Make the account yourself. Type the card only on the provider's site. Do not send passwords, cards, or codes in chat.

**First choice: Vultr, about $5/month.**

1. Open https://www.vultr.com/pricing/ and sign up.
2. Deploy **Cloud Compute**.
3. Location: **Singapore**.
4. Type: **Regular Performance** (not High Performance, not a GPU).
5. Plan: **1 vCPU / 1 GB RAM / 25 GB**.
6. Image: **Ubuntu 24.04 LTS x64**.
7. Skip backups and other paid extras.
8. Check the monthly total. If this plan is not offered in Singapore, stop and use DigitalOcean below.

**If Vultr's $5 plan is not there: DigitalOcean, $6/month.**

1. Open https://www.digitalocean.com/pricing/droplets
2. Create a Droplet: **Basic**, **Regular**, **1 GiB RAM / 1 vCPU / 25 GiB**, **Singapore**, **Ubuntu 24.04 x64**.
3. Do not pick the $4 / 512 MiB plan.
4. Skip backups and extras. Check the monthly total before you confirm.

Wait until the server says it is running. Leave the IP and the root password on your phone. Do not send them in chat.

## 2. Open a terminal on the server

Either:

- the provider's **web console** (the screen icon on the server page), or
- the **Termius** app: New Host, the server IP, user `root`, and the password or key the provider showed once.

## 3. Paste one command

Paste this whole line, then press return:

```
curl -fsSL https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/main/deploy/install.sh | sudo bash
```

It installs for a few minutes. Leave the screen open.

## 4. Enter the three secrets

The installer then asks three questions. **Nothing you type is shown.** A blank line is normal. Press return after each one.

Have these ready from the desk you already run. Copy them on your phone, then paste each one. Do not send them in chat, and do not put them in the command above.

1. Telegram bot token
2. GitHub token (the one that updates the app)
3. DATA_PATH (the private part of your desk link)

Each accepted answer prints `accepted`.

If the installer says the secrets file is already there, it kept the old one and did not show it.

## 5. Leave the desk stopped

The last lines say the desk is **STOPPED**. That is correct.

Do not start it while the old desk is still on. Two desks at once will fight over Telegram and the app. The person moving the desk starts this one after the old one is off. That procedure is `deploy/CUTOVER.md`.

## 6. Check Telegram

After they tell you this desk is on, open Telegram. You want a message from the desk, and the app should show **PAPER**.

If nothing arrives, say so. Do not send a screenshot of the secrets file.

Wrong secret: they delete `/etc/fomo-desk/env` on the server and you run the same command again. Do not open that file.

The server clock is Asia/Jakarta (WIB). An always-on server avoids the old computer sleeping. It does not remove internet outages, and it does not make PAPER results into real trades.
