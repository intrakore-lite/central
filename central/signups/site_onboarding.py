"""Onboarding steps 3 and 4: Central configures the customer's new site through its onboarding API.

The site app `intrakore_master.cloud_onboarding` (PLAT-738) answers POST calls under
`/api/method/intrakore_master.cloud_onboarding.<name>`. A call must carry the header
`X-Intrakore-Onboarding-Secret`, equal to the site config key `intrakore_onboarding_secret`.

Central makes the secret when it creates the server of a site. It goes to the machine in the
`pilot-common-site-config` boot value, because Pilot's site configuration API refuses keys that
look like secrets. The machine runs one site, so its common site config is that site's config.
Central keeps the secret encrypted: on the creation request until the Site record exists, then
on the Site (`onboarding_secret`).

Nothing here logs the secret, the request body or the response body."""

from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING, Any

import frappe
import requests
from frappe import _
from frappe.utils.password import get_decrypted_password, remove_encrypted_password, set_encrypted_password

if TYPE_CHECKING:
	from central.infrastructure.doctype.site.site import Site

HEADER = "X-Intrakore-Onboarding-Secret"
METHOD_PATH = "/api/method/intrakore_master.cloud_onboarding.{0}"
SECRET_FIELD = "onboarding_secret"
SECRET_BYTES = 32
# Connect quickly; complete_setup and invite_members do real work on a small machine.
TIMEOUT_SECONDS = (5, 60)
# A 5xx is retried with these waits. A 4xx never is: the site counts each refused call, and
# locks Central out after 10 in 10 minutes.
RETRY_WAITS = (0.5, 1.5)
MAX_INVITES = 200
MODULES = ("crm", "estimation", "both")
ROLES = ("Admin", "Estimator", "Sales Rep", "Sales Manager")
# The company currency and time zone of a GCC country. Others take the site's defaults.
COUNTRY_DEFAULTS = {
	"United Arab Emirates": ("AED", "Asia/Dubai"),
	"Saudi Arabia": ("SAR", "Asia/Riyadh"),
	"Qatar": ("QAR", "Asia/Qatar"),
	"Kuwait": ("KWD", "Asia/Kuwait"),
	"Bahrain": ("BHD", "Asia/Bahrain"),
	"Oman": ("OMR", "Asia/Muscat"),
	"India": ("INR", "Asia/Kolkata"),
}


class SiteOnboardingError(Exception):
	"""The site did not do what Central asked. `message` is safe to show to the customer."""

	status: int | None = None

	def __init__(self, message: str, status: int | None = None):
		super().__init__(message)
		self.message = message
		self.status = status


class SiteUnavailable(SiteOnboardingError):
	"""The site did not answer, or answered 5xx after the retries. Try again later."""


class SiteRefused(SiteOnboardingError):
	"""The site refused the onboarding secret (403)."""


class SiteRateLimited(SiteOnboardingError):
	"""The site refuses Central for a while after too many failed calls (429)."""


class SiteRejected(SiteOnboardingError):
	"""The site refused the request itself, such as a value it does not accept."""


# --- the secret -------------------------------------------------------------------------------


def new_secret() -> str:
	return secrets.token_urlsafe(SECRET_BYTES)


def get_boot_site_config(action) -> dict:
	"""The site config keys of a site creation, for the machine's boot config. The secret is
	stored on the creation request, so a second build of the same request sends the same one."""
	if action.resource_type != "Site":
		return {}

	secret = (
		get_decrypted_password("Resource Action", action.name, SECRET_FIELD, raise_exception=False)
		or new_secret()
	)
	set_encrypted_password("Resource Action", action.name, secret, SECRET_FIELD)

	# get_bootstrap_metadata adds the seat cap, max_system_users, for every team with seats. When
	# the site is ready, push_site_seat_limit writes it into the site's own config as well.
	return {"intrakore_onboarding_secret": secret, "intrakore_cloud_onboarding": 1}


def push_site_seat_limit(site: Site) -> None:
	"""Write the team's seat count as `max_system_users` into the new site's own config, so the
	cap holds even where the image's site config would hide the boot value. Seat billing sends
	it again on every seat change."""
	from central.billing.catalog.seats import push_user_limit

	if seats := frappe.db.get_value("Team", site.team, "seats"):
		push_user_limit(site, seats)


def adopt_action_secret(site: Site, action_name: str | None) -> None:
	"""Move the secret of the creation request onto its new Site record."""
	if not action_name:
		return

	secret = get_decrypted_password("Resource Action", action_name, SECRET_FIELD, raise_exception=False)
	if secret:
		site.onboarding_secret = secret
		remove_encrypted_password("Resource Action", action_name, SECRET_FIELD)


# --- the client -------------------------------------------------------------------------------


class SiteOnboardingClient:
	"""POST calls to one site's onboarding API."""

	def __init__(self, url: str, secret: str, session: requests.Session | None = None):
		self.url = url.rstrip("/")
		self.secret = secret
		self.session = session or requests.Session()

	@classmethod
	def for_site(cls, site: Site) -> SiteOnboardingClient:
		secret = site.get_password(SECRET_FIELD, raise_exception=False)
		if not secret:
			raise SiteRefused(
				_("This site was created before onboarding from Central. Set it up in the site.")
			)
		# The automatic address answers before and after the rename onto the customer's name.
		return cls(site.url, secret)

	def get_state(self) -> dict:
		return self.call("get_state")

	def complete_setup(self, profile: dict) -> dict:
		return self.call("complete_setup", {"profile": profile})

	def invite_members(self, rows: list[dict]) -> dict:
		return self.call("invite_members", {"rows": rows})

	def apply_master_setup(self, config: dict) -> dict:
		return self.call("apply_master_setup", {"config": config})

	def call(self, method: str, payload: dict | None = None) -> Any:
		url = f"{self.url}{METHOD_PATH.format(method)}"
		for attempt in range(len(RETRY_WAITS) + 1):
			try:
				response = self.session.post(
					url,
					json=payload or {},
					headers={HEADER: self.secret, "Accept": "application/json"},
					timeout=TIMEOUT_SECONDS,
					allow_redirects=False,
				)
			except (requests.ConnectionError, requests.Timeout):
				raise SiteUnavailable(
					_("Your workspace is not answering yet. Try again in a minute.")
				) from None

			if response.status_code < 500 or attempt == len(RETRY_WAITS):
				return self.read(method, response)
			time.sleep(RETRY_WAITS[attempt])

	def read(self, method: str, response: requests.Response) -> Any:
		status = response.status_code
		if status == 403:
			raise SiteRefused(_("Your workspace refused Central's onboarding key. Contact support."), status)
		if status == 429:
			raise SiteRateLimited(
				_("Your workspace is refusing calls for a few minutes. Try again later."), status
			)
		if status >= 500 or status in (301, 302, 404):
			# A 404 or a redirect means the site is not serving the API yet, such as during a rename.
			raise SiteUnavailable(_("Your workspace is not ready yet. Try again in a minute."), status)
		if status >= 400:
			raise SiteRejected(error_message(response) or _("Your workspace refused the request."), status)

		try:
			body = response.json()
		except ValueError:
			raise SiteUnavailable(_("Your workspace answered with something unexpected."), status) from None
		return body.get("message") if isinstance(body, dict) else None


def error_message(response: requests.Response) -> str | None:
	"""The message Frappe shows for a refused call: the last `_server_messages` entry, else
	`exception` without its class name."""
	try:
		body = response.json()
	except ValueError:
		return None
	if not isinstance(body, dict):
		return None

	try:
		messages = frappe.parse_json(body.get("_server_messages") or "[]")
		if messages:
			last = frappe.parse_json(messages[-1])
			text = last.get("message") if isinstance(last, dict) else str(last)
			if text:
				return frappe.utils.strip_html(text)[:300]
	except Exception:
		pass

	exception = body.get("exception")
	if isinstance(exception, str) and exception:
		return exception.split(":", 1)[-1].strip()[:300]
	return None


# --- what Central sends -----------------------------------------------------------------------


def site_profile(team: str) -> dict:
	"""The step 1 answers as the site's setup profile: the owner, the company and its defaults."""
	values = frappe.db.get_value(
		"Team",
		team,
		["team_name", "owner_user", "business_type", "headcount_bracket", "turnover_band"],
		as_dict=True,
	)
	billing = (
		frappe.db.get_value(
			"Billing Profile",
			team,
			["legal_name", "phone", "address_line1", "address_line2", "city", "country", "tax_id"],
			as_dict=True,
		)
		or frappe._dict()
	)
	owner = values.owner_user
	profile = {
		"full_name": frappe.db.get_value("User", owner, "full_name") or owner,
		"email": owner,
		"company_name": billing.legal_name or values.team_name,
		"mobile": billing.phone,
		"country": billing.country,
		"business_type": values.business_type,
		"headcount_bracket": values.headcount_bracket,
		"turnover_band": values.turnover_band,
		"trn": billing.tax_id,
	}
	if billing.country in COUNTRY_DEFAULTS:
		profile["currency"], profile["timezone"] = COUNTRY_DEFAULTS[billing.country]
	if billing.address_line1:
		profile["address"] = {
			"line_1": billing.address_line1,
			"line_2": billing.address_line2,
			"city": billing.city,
		}

	return {key: value for key, value in profile.items() if value}


def validated_rows(rows: list) -> list[dict]:
	"""The invitations with their fields trimmed, or a refusal naming the first bad row."""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Add at least one member to invite."), frappe.ValidationError)
	if len(rows) > MAX_INVITES:
		frappe.throw(_("Invite at most {0} members at once.").format(MAX_INVITES), frappe.ValidationError)

	cleaned = []
	for number, row in enumerate(rows, start=1):
		row = row if isinstance(row, dict) else {}
		email = (row.get("email") or "").strip().lower()
		if not frappe.utils.validate_email_address(email):
			frappe.throw(_("Row {0}: enter a valid work email.").format(number), frappe.ValidationError)
		modules = (row.get("modules") or "").strip().lower()
		if modules not in MODULES:
			frappe.throw(_("Row {0}: choose CRM, Estimation or both.").format(number), frappe.ValidationError)
		role = (row.get("role") or "").strip()
		if role not in ROLES:
			frappe.throw(_("Row {0}: choose a role.").format(number), frappe.ValidationError)
		cleaned.append(
			{
				"full_name": (row.get("full_name") or "").strip()[:140],
				"email": email,
				"modules": modules,
				"role": role,
			}
		)

	return cleaned


CONFIG_KEYS = {
	"crm": ("lead_sources", "bid_weights", "deal_currency", "pipeline_stages", "threshold"),
	"estimation": ("uom_system", "templates", "net_margin_pct", "overhead_pct", "labour_rate_base"),
}


def validated_config(config: dict | str) -> dict:
	"""The master setup with only the sections and keys the site knows."""
	config = frappe.parse_json(config) if isinstance(config, str) else config
	if not isinstance(config, dict):
		frappe.throw(_("The master setup is not valid."), frappe.ValidationError)

	cleaned = {}
	for section, keys in CONFIG_KEYS.items():
		values = config.get(section)
		if isinstance(values, dict):
			cleaned[section] = {key: values[key] for key in keys if key in values}

	weights = cleaned.get("crm", {}).get("bid_weights")
	if weights is not None:
		if not isinstance(weights, dict) or any(
			not isinstance(value, int | float) or value < 0 for value in weights.values()
		):
			frappe.throw(_("Bid weights must be positive numbers."), frappe.ValidationError)
		if round(sum(weights.values())) != 100:
			frappe.throw(_("Bid weights must add up to 100."), frappe.ValidationError)

	if not any(cleaned.values()):
		frappe.throw(_("The master setup is empty."), frappe.ValidationError)
	return cleaned
