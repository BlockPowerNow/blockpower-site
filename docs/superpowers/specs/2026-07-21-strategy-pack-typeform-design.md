# Strategy Pack signup form -- design

Date: 2026-07-21
Repo: `BlockPowerNow/blockpower-site` (public, GitHub Pages, CNAME `blockpower.org`)

## Problem

The "Get your Strategy Pack" button on blockpower.org points at
`https://husb.link/myblock`. That Rebrandly short link is dead -- it 302s to
`app.rebrandly.com/broken-links`. The primary conversion path on the site has
been going nowhere, and there is no capture of who wants a pack.

This replaces the dead link with a Typeform that collects who the person is,
where to mail their pack, why they want to do it, and how much of their block
they are willing to cover.

## Decisions

| Decision | Choice |
|---|---|
| Scale question | Branch on housing type, then ask scale |
| Fulfillment | Physical mail -- collect full postal address |
| Geography | North Carolina only; other states routed to a separate ending |
| Owning account | Hub3 Typeform account, workspace `eTZb5R` (default "Hub3") |
| c3/c4 handling | Disclosure line naming Hub3 Inc. as the mailer |
| Response handling | Stay in Typeform, self-notification email per response to `karthik@hub3.us` |
| Embed | Popup overlay, with a working `href` underneath as fallback |
| Credentials | 1Password item "Typeform API - Hub3 Account", Dev vault, field `credential` |

## Credentials note

The three Typeform tokens in `~/.env~` (`KHUB3_TYPEFORM_KEY`,
`KARTBALA_TYPEFORM_API_KEY`, `KUS_TYPEFORM_KEY`) all return HTTP 403
`AUTHENTICATION_FAILED` as of 2026-07-21. This is the same failure recorded in
log.org on 2026-05-22, which blocked the hub3-site form wiring at the time.

The 1Password copies of all three work (HTTP 200). 1Password is canonical; the
env file holds rotted copies. Fixing or removing the stale env entries is out of
scope here and is not currently tracked anywhere -- see "Out of scope" below.

## Form structure

Owner: Hub3 account, workspace `eTZb5R`.
Title: "Get your Strategy Pack"

Contact fields come last on purpose. Opening with a name field costs
completions; opening with a one-tap choice does not.

**Welcome screen**

> You vote in every election. That makes you the right person to make sure your
> neighbors do too. Tell us where you are and how much of your block you want to
> cover, and we'll mail you a map of your precinct plus a one-page play.
>
> We're organizing in North Carolina right now. About two minutes.

1. **Where do you live?** (multiple_choice, required)
   - A house or townhouse on a street
   - An apartment or condo building

2. **About how many doors can you cover?** (multiple_choice, required)
   Shown when Q1 = house.
   - 5 -- my closest neighbors
   - 10 -- both sides of my street
   - 50 -- my whole block

3. **How much of your building?** (multiple_choice, required)
   Shown when Q1 = apartment building.
   - Just my floor
   - The entire building

4. **Why do you want to do this?** (long_text, required)
   Helper: "A sentence or two is plenty."

5. **What's your name?** (short_text, required)

6. **Where should we email you?** (email, required)
   Helper: "For your confirmation, and a heads-up when your pack ships."

7. **Phone number** (phone_number, optional)
   Helper: "Only if you'd rather we call or text about your precinct."

8. **Where should we mail your pack?** (group)
   Helper: "Your address is how we find your precinct. Your Strategy Pack is
   mailed by Hub3 Inc., a 501(c)(3) -- signing up here is not a contribution to
   Block Power. We never share your information with a campaign or party unless
   you authorize it."
   - Street address (short_text, required)
   - Apartment or unit (short_text, optional)
   - City (short_text, required)
   - State (dropdown, required) -- all 50 states
   - ZIP code (short_text, required)

The Typeform Create API has no native `address` field type. The enum includes
`contact_info` and `phone_number` but not `address`, so the mailing address is
an explicit field group. Separate fields also make the CSV export mail-merge
ready without parsing.

**Ending A -- North Carolina** (State = NC)

> Thanks -- we've got it. We'll build your precinct map and mail your Strategy
> Pack. Watch your email for a confirmation. If anything's wrong with your
> address, reply to it and we'll fix it.

**Ending B -- everywhere else** (State != NC)

> Thanks for signing up. We're only organizing in North Carolina right now, so we
> can't build your precinct map yet. We'll hold your details and email you when
> we reach your state.

Routing on the state field rather than gating up front means an out-of-state
person still leaves an email address, and gets told the truth instead of a
confirmation the org cannot honor.

## Site change

One file, `index.html`. Line 435 today:

```html
<a class="btn" href="https://husb.link/myblock" target="_blank" rel="noopener">Get your Strategy Pack <span class="arrow">-></span></a>
```

Becomes:

```html
<a class="btn" href="https://form.typeform.com/to/<FORM_ID>"
   data-tf-popup="<FORM_ID>" data-tf-size="100"
   target="_blank" rel="noopener">Get your Strategy Pack <span class="arrow">-></span></a>
```

Plus `<script src="//embed.typeform.com/next/embed.js"></script>` before the
closing `</body>` tag.

The `href` stays real. If the Typeform script fails to load or is blocked, the
button still opens the hosted form in a new tab instead of doing nothing. That
is the failure mode this change exists to fix, so it should not be reintroduced
by the fix itself.

Nothing else on the page moves. The `.btn` styling, the arrow span, and the
surrounding copy are unchanged.

## Accessibility

The page is built low-vision first (20px base, high contrast). The Typeform
popup renders at `data-tf-size="100"` (full viewport) rather than a small modal,
and Typeform's own type scale is large by default. Verify contrast and text size
on the rendered form before calling this done; if the theme reads small, set a
custom Typeform theme rather than shrinking the page to match.

## Testing

1. `python3 -m http.server` against the local clone; confirm the button opens
   the popup and that the page still renders unchanged otherwise.
2. Submit a North Carolina test response. Confirm ending A, confirm the
   notification email arrives.
3. Submit a non-NC test response. Confirm ending B.
4. Submit one house-path and one building-path response. Confirm the branch
   lands in separate columns in the export.
5. Block `embed.typeform.com` in devtools, reload, click the button. Confirm it
   opens the hosted form in a new tab rather than failing silently.
6. After deploy, load blockpower.org and repeat step 1 against production.
7. Delete the test responses.

## Out of scope

Nothing below is tracked anywhere yet. Each needs an owner and a date, or it
will be lost.

- The footer `Privacy` and `Terms` links are still `#` stubs. Collecting home
  addresses without a privacy policy is a real gap, but it is separate work from
  wiring the form.
- Mail fulfillment itself -- who prints the maps, who stuffs envelopes, what the
  turnaround is. The form promises a mailed pack; that promise needs an owner.
- The stale Typeform tokens in `~/.env~`.
- Repointing `husb.link/myblock`, which stays broken for anyone who has the old
  link. Worth redirecting it at the new form separately.
