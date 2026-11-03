# Signups

## Purpose

The Signups module holds what a new customer gets: the [Product](doctype/product/SPEC.md) they sign up for, the free trial and the welcome credit. Operators start with the [Trials operator guide](../../spec/TRIALS_OPERATOR_GUIDE.md).

## Invite-only access

Central Settings > Trials > **Invite Only** is on by default. When it is on:

- A new email gets no sign-in code unless it has a live Trial Invitation or a pending team invitation. Central answers with the `INVITE_ONLY` message of `central/errors.py`: "Intrakore Cloud is invite-only. Ask your Intrakore contact for an invitation." `central.users.require_invitation` holds this rule, and `create_user` checks it again.
- An existing user signs in as before.
- `/try` and `/dashboard/signup` open the sign-in page, and the sign-in page shows no signup link.

Turn it off to restore the public signup and the trial link.

### Trial Invitation

An operator invites a person from the **Trial Invitation** list in Desk (Signups workspace) or through `central.api.trial_invitations`. Saving a new invitation emails a one-time link, `https://intrakore.cloud/dashboard/activate?token=<token>`, from the default outgoing email account.

| Field | Meaning |
|---|---|
| Email, Full Name, Company | The invitee. Full Name becomes the account name. |
| Product, Lead Reference | The product to try, and the lead in the Intrakore CRM. |
| Status | Sent, Accepted, Expired or Revoked. |
| Expires On | Now plus Central Settings > Trial Invitation Expiry (Days), 7 by default. |
| Team | The first team the invitee creates after activation. |

Central stores only the SHA-256 of the token. Accepting, revoking and the daily expiry job clear the hash, so a link works once. Resend issues a new token and a new expiry, and the earlier link stops working. An invitation for an email that already has a Sent invitation updates that invitation and resends it.

### Activation

The activation page shows the invitation and asks the person to activate. A page load does not spend the link, so a mail scanner that opens the link does not use it.

- A new email: the link proves the mailbox as a sign-in code does. Central creates the user, signs them in, marks the invitation Accepted and opens `/dashboard/onboarding/profile`.
- An email that already has an account: the person signs in with a code first, then the link is spent. A link alone never opens an existing account.
- A session for another email: the page asks the person to sign out.

A new invitee who signs up with a code instead of the link also accepts the invitation and goes to the same onboarding page.

### Operator API

Call it with the API key and secret of a System Manager. Every method refuses other users. `invite` and `resend` accept 120 calls an hour from one IP address.

| Method | Arguments | Result |
|---|---|---|
| `invite` (POST) | `email`, `full_name`, `company`, `product`, `lead_reference` | The invitation summary |
| `resend` (POST) | `name` | The summary, with the new expiry |
| `revoke` (POST) | `name` | The summary |
| `status` (GET) | `email` or `name` | The newest summary for the email, or null |
| `list` (GET) | `status`, `email`, `lead_reference`, `start`, `page_length` | Invitations, newest first |

Example: `curl -X POST -H "Authorization: token <key>:<secret>" https://intrakore.cloud/api/method/central.api.trial_invitations.invite -d email=jane@acme.ae -d full_name="Jane Doe" -d company="Acme LLC" -d lead_reference=CRM-LEAD-2026-00012`

## Welcome credit

Grant Welcome Credits is off by default, so no team gets a welcome credit: a product signup gets a free trial site instead, and every other server needs a payment method. When an operator turns it on, a Team gets the welcome credit when its first payment method becomes active, not at signup. The credit is granted once for each owner across all of the owner's Teams.

A Team that had a free trial gets no welcome credit, because the trial site is its free start. `is_welcome_credit_due` holds this rule. A card does not end a trial: it pays for the site from the trial end date.

| Billing Settings field | Value on a new install |
|---|---|
| Grant Welcome Credits | Off |
| Welcome Credit Amounts | 10 USD, 1000 INR |
| Validity (Days) | 60 |

A new install seeds these values once. Change them on an existing site in Billing Settings. A currency with no amount gets no credit. A staging trial team (Billing Settings, Provision Teams as Trial) still gets its credit at signup, because it runs servers on credit before it has a payment method.

### Operator credit

A System Manager can grant credit from the **Grant Credit** action on a Team, for example 100 USD to a beta user. The operator sets the amount in the Team's billing currency, the validity in days and a note. The credit is available at once. It counts as the owner's welcome credit, so the Team gets no welcome credit later.

## Trials

A trial site is a site from a Product's signup flow, for a Team that has never paid. An invited Team stores its card before Central builds its site, and still gets the trial. A direct Central signup has no free trial: it lands in the console, adds a payment method and buys its servers. Only a signup link with `?product=` opens the onboarding pages, and `create_trial_site` needs a product. It runs free for a set number of days. The trial state is on the Site, in the **Trial** section.

A Team has paid when it has a Subscription, or an Invoice that is not Draft or Cancelled. Such a Team gets no free trial, also when its payment method has expired or failed. So a Team with unpaid invoices cannot open free servers. When such a Team follows a signup link, the signup page does not ask for a site name. It says that the Team buys its servers and links to the New Server page.

### Configuration

| Field | Where | Meaning |
|---|---|---|
| Trial Days | Central Settings (Trials tab), and Product | Days a trial site runs from when Central records it. 30 on a new install. A Product with 0 uses Central Settings. |
| Trial Deletion Days | Central Settings (Trials tab), and Product | Days a stopped trial site is kept before its server is terminated. A Product with 0 uses Central Settings. |
| Trial Notice Days | Central Settings (Trials tab) | Days before the end date, and before the deletion date, that the warning email goes out. |
| Default Trial Product | Central Settings (Trials tab) | The product of the free trial that the sign-in page offers and that `/try` opens. Empty hides the offer and sends `/try` to the plain signup. A disabled product counts as empty. |

Example: Central Settings has Trial Days 7 and Trial Deletion Days 7. Product `raven` has Trial Days 14. A Raven trial runs 14 days, stops, and is terminated 7 days later.

### Trial link

When Invite Only is off, `/try` is the short link for the marketing site, for example `https://intrakore.cloud/try?utm_source=intrakore.com`. It sends a 302 redirect to `/dashboard/signup?product=<Default Trial Product>` and keeps every query parameter, so the console records the UTM tags and the referrer as the team's first touch. A `product` in the link wins over the setting. The sign-in page shows **Start your free N-day trial** to a visitor without a product link. Both read `central/signups/trial_offer.py`.

### Operation

Central records the site when the region first reports its machine with an address, a few minutes after the request. The trial starts then. It does not wait for the customer to open the site, so a trial that the customer leaves also ends.

A free-trial server also boots with a Grove key from the pool [AI Settings](../services/doctype/ai_settings/SPEC.md) keeps for its product, when that pool has one, so the site's apps can call AI before the team has AI of its own.

| Trial State | When | What Central does |
|---|---|---|
| Active | Central records the site and its creation request is a free trial | Sets Trial Ends On. A payment method added before or during the trial does not convert it early. |
| Converted | Central records the site and its creation request is not a free trial | Nothing. The site is not a trial. |
| Converted | Trial Ends On is reached, the Team has an active payment method and has not cancelled, and the plan fits the spending limit | Starts billing. See [Billing and conversion](#billing-and-conversion). |
| Ended | Trial Ends On is reached otherwise | Stops the server and sets Trial Deletes On. |
| Deleted | The server is Terminated: on Trial Deletes On, or when the customer terminates it earlier | On Trial Deletes On, asks for a normal terminate action each day until the server is Terminated. A server with termination protection on is kept, and Trial Error says why. Sets the state when the server is Terminated, so the owner can start a new trial at once. |

The `Trial` class in `central/signups/trial.py` owns these states. Every change goes through `Trial.move_to`, which refuses a change that its transition table does not allow. The daily job `central.signups.trial.run_trials` moves each site. It sends each email once and records the last one in Trial Last Notice.

| Event | Sent |
|---|---|
| `trial_unopened` | Once, from the day after the site is ready, when nobody has opened it. Not sent when a warning is due. |
| `trial_expiring` | Trial Notice Days before Trial Ends On, and again on the last day. A Team with a card on file gets it only on the last day, with its first payment: the seats, the amount before tax and the date. Its button opens Settings > Billing. |
| `trial_ended` | When the stop job has stopped the server, not when the trial ends |
| `trial_deletion_soon` | Trial Notice Days before Trial Deletes On |
| `trial_deleted` | When the server is terminated. Its button opens the signup page of the same product. |
| `trial_converted` | When the trial converts on its end date, or when Keep this site converts an Ended trial |

The `trial_expiring`, `trial_ended` and `trial_deletion_soon` emails link to the server's Upgrade dialog (`/servers/<server>?action=resize`). That dialog adds a payment method and, for an Ended trial, keeps the site. A payment method added on Billing does not keep an Ended trial.

A Product can add its own paragraph to each email and show its own logo and name. See [Product emails](doctype/product/SPEC.md#emails). These events are in the **Trial** notification category. A user can turn the email or the in-app notice for this category off in their notification settings. Each event goes to the Team members who hold `billing:view`.

A trial server usually sleeps when idle, and Atlas does not stop a sleeping VM. To end a trial, Central starts the server and then stops it. An explicit stop keeps the VM down, so traffic does not wake it.

### Limits

| Request | What Central checks |
|---|---|
| A trial site from the signup flow, Team that has no payment method and has never paid | The Team's owner has fewer open trial sites (Active or Ended), pending trial site creations, and provisioned trial servers whose site Central has not recorded yet, across all the owner's Teams, than Central Settings, Trial Servers Limit. A new Team gives no new trials. No credit is needed. Otherwise Central refuses with `TRIAL_IN_PROGRESS`, which names the open trial. |
| Any other server | A Team with an overdue invoice, or a subscription that is Past Due or Suspended, is refused with `PAYMENT_OVERDUE`. Otherwise credit covers the server's monthly rate, or the billing profile is complete and the Team has an active payment method, or the Team pays by Manual Checkout and has already paid one invoice by gateway. Otherwise Central refuses with `PAYMENT_METHOD_REQUIRED`. With Central Settings, Require Payment Method for Servers off, a complete billing profile is enough. |
| Start an Ended trial's server | Refused. The Team adds a payment method and then chooses Keep this site, which converts the trial and starts the server. |
| Resize a trial server | Not done. A trial server has no subscription. On an open trial, `central.api.servers.resize_server` (which also needs `billing:manage`) and `billing_api.change_plan` keep the plan in Conversion Plan on the Site and resize nothing. The plan must be one of the trial's plan choices. `get_composed_config` returns `trial` and `trial_plans`. |

### Signup with an open trial

`central.api.sites.get_open_trial(team)` returns the owner's oldest open trial across all the owner's Teams, or null. The signup page reads it before it asks for a site name, so it can offer that site instead. It returns `site`, `server`, `address`, `url`, `product`, `product_title`, `product_logo`, `state`, `ends_on` and `deletes_on`. While the first site is still being set up, it returns only `state` (Setting up) and the product fields. A caller who cannot view the trial's Team gets the same fields only, so a site of another Team is not named. It needs `server:create`.

| Open trial | What the customer can do |
|---|---|
| Active | Open the site, and install another product's app there. |
| Ended | Keep the site, or terminate its server. A terminated trial is Deleted at once, so a new trial can start. |

### Another product's app on the open trial site

`TrialAppInstall` in `central/signups/app_install.py` adds a product's app to the owner's Active trial site, so one free site runs both products. The enabled Product gives the app (Signup App), the title, the logo, the Setup Messages and the landing page.

| Step | API | What happens |
|---|---|---|
| Start | `install_trial_app(product, team)` | Central reads the site's apps from Pilot. When the site has the app, it returns `success` and no task. Otherwise Pilot queues the install, and Central adds a comment on the Site with the Pilot task. |
| Progress | `get_trial_app_install(site, task_id, product, team)`, a POST every 3 seconds | Returns `status` (queued, running, success, failed, or unreachable when the site did not answer this time), `queue_position` and `started_at`. |
| Open | `login_site(name, product)` | Signs in on the Product's Landing Route. |

| Failure | Customer sees | Operator sees |
|---|---|---|
| The site does not answer at start | "Your site did not answer. Wait a minute, then try again." | Error Log "Trial app install failed" |
| The site does not answer for 2 minutes of polls | "Your site stopped answering. Try again in a few minutes." | Nothing new. Pilot keeps the task. |
| The Pilot task fails | "CRM could not be installed on your site." with Try again and Open my site | Error Log and a comment on the Site with Pilot's reason |

### Server access

An open trial (Active or Ended) gives the customer the site, not the server. A free trial whose site Central has not recorded yet is locked too, because its creation request says it is a free trial. `VirtualMachine.require_server_access` refuses these routes with a permission error until the trial converts:

| Route | Entry point |
|---|---|
| Set the server's SSH keys | `VirtualMachine.set_ssh_keys` |
| Web console, SSH or TTY | `central.integrations.servers.get_console_url` |
| Pilot sign-in, also "Open server" in the site | `VirtualMachine.get_bench_login_url` |
| Snapshot, also the final snapshot on terminate | `central.api.snapshots.take_snapshot`, `submit_command` |
| Termination protection | `VirtualMachine.set_termination_protection` |
| GitHub connect for the server's Pilot | `GitHubConnectionAttempt.bind` |

A System Manager keeps access. A Team SSH Key sync skips a locked server, so its keys never reach it. The daily automatic snapshot skips a locked server too. A trial server starts with no SSH keys. Site sign-in (`claim_site`, `login_site`) stays open. The console registry returns `is_access_locked` on each server, so the console hides these actions.

`central.api.pilot.get_server_access` returns `is_locked` for the server of the calling Pilot credential. It is for Pilot, which must refuse the site's config edits and config downloads while the server is locked. A credential whose server is not linked yet reads as locked.

A team with a locked server also gets no LLM and no object storage, because both cost money. `central.signups.access.require_service_access` refuses `enable_ai` and `create_bucket`, the only ways in. The console shows the refusal message. A System Manager keeps access.

### Console

`central.billing.api.dashboard.account.get_billing_profile` returns `payment_method_required` and `welcome_credit` (`amount`, `currency`, `validity_days`, or null when the owner already had it). It also returns `open_trial`: the team's own oldest open trial (`state`, `server`, `product`, `product_title`, `plan`), or null. `server` is null for a caller without `server:view`. The Billing page and the onboarding payment step show it: an Active trial converts on its end date when a payment method is on file, and an Ended trial is kept only from the Upgrade dialog. When a payment method is required, the New Server page shows a note and disables Create. Its **Add payment method** button opens the billing details dialog when they are missing, then the payment method dialog, on the same page. The welcome credit offer needs a billing currency, and the currency comes from the country (India pays in INR, every other country in USD). So the onboarding payment step asks for the billing country first and saves it to the billing profile. It fills India when the browser time zone is in India. It then names the welcome credit in that currency, says that adding a payment method does not charge it, and opens the same two dialogs, with the country already filled. On Billing, the main action for a new team is **Add card**. **Add credit** on the Wallet row tops up the prepaid wallet.

### Billing and conversion

A trial server has no subscription, so a trial creates no invoice. Central decides once, when the signup sends its creation request, whether the site is a free trial. It stores the answer in Free Trial on the Resource Action. Every later step reads that value and does not check the payment method again, so a card added or removed during creation does not change it. The daily backfill of missing subscriptions skips these servers too.

A payment method does not convert a trial when it becomes active. On Trial Ends On, the daily job converts an Active trial when the Team has an active payment method and has not cancelled (Subscription Ends On on the Team is empty). Otherwise the trial ends. An Ended trial stays Ended and stopped, so a card added for one product does not start and bill a site the customer left. To keep an Ended trial, a member with `billing:manage` chooses **Keep this site** in the console resize dialog (`central.api.servers.keep_trial_site`). It converts that one site and starts its server. Its deletion date applies until then.

Each conversion must fit the Team's spending limit: the trust-tier cap minus the monthly rate of its running subscriptions and of its converted trials whose servers are not terminated and have no subscription yet. The check runs under a lock on the Team, so two conversions cannot use the same part of the limit. A trial whose plan does not fit is not converted, and it ends on its end date. The customer can then keep it with Keep this site, which applies the same check.

A site becomes Converted in these steps:

1. Central records Trial Cost: the server's plan's monthly rate, divided by 30, for each day since Central recorded the site.
2. A running or sleeping server gets its subscription now. A stopped server gets it when it starts. A server on a trial plan gets it when it runs its paid plan, so the trial plan is never billed. Until then, `get_composed_config` returns `starting`, and the console resize dialog says the server is moving to its paid plan and checks again.
3. A background job moves a server on a trial plan to its paid plan with a normal resize, which also turns idle sleep off and starts the server. The resize has no subscription to re-lock, so the server opens its subscription on the paid plan when the resize is done. For a server on any other plan, the job turns idle sleep off in Atlas, and starts the server when it is Stopped. When the team pays while the trial's stop job runs, the stop job queues this job again, so the server does not stay stopped. When a resize of the server is pending, the job writes a Trial Error and stops, because both jobs change the server's power. The daily job sends the conversion again.

A plan marked Available on Trial is a trial plan. Only a free trial site starts on one, and every paid plan list leaves it out (`get_server_plans`). A trial on a trial plan converts onto a paid plan: the Site's Conversion Plan, which the customer picks in the in-app billing panel or the console Upgrade dialog, or else the cheapest plan in the trial's plan choices (`Trial.get_conversion_plan`). The plan choices are the paid plans that the team may resize to, no smaller than the trial plan, cheapest first (`Trial.get_plan_choices`). A trial on any other plan converts on it.

A trial is priced at the catalog rate of the plan it converts to, in the team's currency and the server's region, which is the rate its subscription charges. The rate reserved on the creation request is not its price: the customer accepted no quote at signup, the currency at signup is a guess before the billing profile exists, and a subscription keeps its opening rate. The spending-limit check, the rate held for a starting server, Trial Cost and the Upgrade dialog all use this one rate (`Trial.get_monthly_rate`).

The plan menus of a trial server (the plan choices, console resize and in-app Change plan) leave out every plan with less vCPU or memory than the plan the trial was created on, because the product site needs at least that much (`get_trial_plan_floor`).

A Deleted trial is not converted, because its server is gone. Its Trial Cost runs to Trial Ends On.

### Seats

A product site of a Team with seats is billed per seat, not by its server plan. The customer chooses the seats at onboarding and changes them in Settings > Billing. `central/billing/catalog/seats.py` owns the rules.

| Setting | Where | Meaning |
|---|---|---|
| Seats | Team | The seat count. 0 means the site is billed by its server plan. |
| Seat Price | Catalog Rate of the Product, then Catalog Rate of the Users resource type, then Central Settings (Trials tab) | The monthly price of one seat, in the Team's billing currency. 0 turns seat billing off. |
| Included Seats | Central Settings | The least number of seats that is billed. |
| Storage Price per GB, Included Storage (GB) | Central Settings | Storage above the included storage, per GB a month. Not billed yet: metering does not record the server's used disk. |

| Event | What Central does |
|---|---|
| The server's subscription opens | The segment locks max(Seats, Included Seats) × Seat Price in place of the plan's rate (`Subscription.get_rate_snapshot`). |
| A seat change on a paid site | A Plan Changed segment at the new price, from now. The billing run bills each segment by the day. A larger count must fit the spending limit. |
| Any seat change | A background job writes `max_system_users` = Seats into the site's config through Pilot (`PATCH /api/v1/sites/<site>/configuration`), and resizes the server as the system when the seat band changes: 1 to 5 seats `plan-1vcpu`, 6 to 15 `plan-2vcpu`, 16 to 40 `plan-4vcpu`, 41 or more `plan-8vcpu`. The disk never shrinks. A failed write is a comment on the Site and an Error Log. |
| A new server | Its boot config carries `max_system_users` when the Team has seats. |
| Cancel during the trial | Subscription Ends On is the trial end date. The trial ends on that date with no charge, and the normal end, stop and delete steps follow. |
| Cancel on a paid site | Subscription Ends On is the last day of this month. The daily job `run_cancellations` closes billing at the end of that day and stops the server. It terminates the server after the trial deletion days. Keep subscription clears the date before then. |

The console routes are `billing.api.dashboard.get_seats`, `change_seats` and `set_subscription_cancelled`. Reads need `billing:view`, changes need `billing:manage`. A customer never needs `server:resize`.

### Upgrade dialog

The console's Upgrade dialog on a trial server lists the trial's plan choices with their monthly rates, with the Conversion Plan or the cheapest one selected. **Add payment method**, **Keep this site** and, for a held trial, **Use this plan** first save the selected plan. After the payment method is added, the dialog checks the trial again every 5 seconds for 2 minutes. While the server moves to its paid plan, the dialog says so. An Ended trial is only kept: **Keep this site** moves the server to the selected plan and starts it.

### In-app status

`central.billing.api.billing_api.get_billing_summary` returns `trial` for the site on the calling server: `state` (Active or Ended), `can_keep` (Ended, the Team has an active payment method, and the caller has `billing:manage`), `held` (Active, and the Team has an active payment method, so the trial converts on its end date), `seats` (the seat price, see [Seats](#seats), or null), `ends_on`, `days_left`, `deletes_on` and `plan`. `plan` is the plan the site converts to: `name`, `title`, `monthly_rate` (the plan's catalog rate in the team's currency and the server's region, which the subscription charges) and `currency`, or null when the site has no creation request. `trial` is null when the site has no open trial. The in-app billing panel also reads these values:

| Value | Meaning |
|---|---|
| `plan_change` in `get_billing_summary` | The pending resize of the server, such as the move to the paid plan. `plan` is the plan title. `progress_url` is the waiting page. It is null when no resize is pending. |
| `get_plan_options` on an open trial | The trial's plan choices, cheapest first. `selected` is the plan that the site converts to. |
| `change_plan` on an open trial | Keeps the chosen plan in Conversion Plan. It resizes nothing. | On a server with several sites, the caller passes `site`, the Site's name. Without it, Central refuses the call.

### Desk

On a Site with an open trial, a System Manager has a **Trial** menu: **Extend Trial** adds days and starts an Ended trial again, with the AI key it still holds, **End Trial Now** ends an Active trial today and stops its server (its AI key stays until its days pass or the server is terminated), and **Retry Trial Step** runs today's step again after a Trial Error. On a Converted site, it sends the conversion job again. Each action leaves a comment on the Site. A trial that converts hands its AI key to the team at Grove in the background, best effort: three attempts, then the AI Trial Key record and the Site say it failed, the key is revoked and the team creates its own. The **Trial Sites** report counts trial sites and their cost by product, month and state.

### Failure

When a stop, a terminate, or the conversion job fails, Central writes the reason in Trial Error on the Site and an Error Log, and the daily job tries again the next day. The daily job includes Converted sites that have a Trial Error. While a trial is Ended and its server is not Stopped, the daily job sends the stop again.

### Operator alerts

`central.signups.alerts.alert_failed_signups` runs every hour. When a signup site creation became Failed or Timed Out in the last hour, it sends one message that lists them, through the operator alert channel in Billing Settings (Raven, or email as a fallback). A signup should never fail, so one failure is enough. The check adds nothing to the signup path.
