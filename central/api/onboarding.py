import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils.translations import _lt

from central.utils.guards import require_capability


@frappe.whitelist(methods=["GET"])
@require_capability(
	"billing:manage", _lt("Only a team admin can set up this team. Ask the team owner to continue.")
)
def get_onboarding(team: str | None = None, product: str | None = None) -> dict:
	"""The product, saved answers, seat prices and trust content of the onboarding pages."""
	from central.signups.onboarding import get_onboarding as read

	return read(team, product)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
@require_capability(
	"billing:manage", _lt("Only a team admin can set up this team. Ask the team owner to continue.")
)
def save_profile(
	full_name: str,
	mobile: str,
	country: str,
	organisation: str,
	business_type: str,
	headcount_bracket: str,
	seats: int,
	turnover_band: str | None = None,
	team: str | None = None,
) -> dict:
	"""Store onboarding step 1 on the Team and its Billing Profile. Team.validate also
	requires team:edit for the new team name."""
	from central.signups.onboarding import save_profile as save

	return save(
		team,
		{
			"full_name": full_name,
			"mobile": mobile,
			"country": country,
			"organisation": organisation,
			"business_type": business_type,
			"headcount_bracket": headcount_bracket,
			"turnover_band": turnover_band,
			"seats": seats,
		},
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60, user_based=True)
@require_capability(
	"server:create", _lt("You can't create sites for this Team. Ask a team admin to review your access.")
)
def start_site(team: str | None = None, product: str | None = None) -> dict:
	"""Queue the team's site after its card is saved. See `central.signups.onboarding.start_site`."""
	from central.signups.onboarding import start_site as start

	return start(team, product)


# Steps 3 and 4 configure the team's own site. Each call needs the same team admin as steps 1 and 2.
SETUP_DENIED = _lt("Only a team admin can set up this team. Ask the team owner to continue.")


# A POST, because a site that answers for the first time is recorded ready and starts its setup.
@frappe.whitelist(methods=["POST"])
@rate_limit(limit=1200, seconds=60 * 60, user_based=True)
@require_capability("billing:manage", SETUP_DENIED)
def site_state(team: str | None = None) -> dict:
	"""Where the team's site is, its seats, and its master setup. See `get_site_state`."""
	from central.signups.onboarding import get_site_state

	return get_site_state(team)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60, user_based=True)
@require_capability("billing:manage", SETUP_DENIED)
def complete_site_setup(team: str | None = None) -> dict:
	"""Run the site's company setup from the step 1 answers again, such as after a failure."""
	from central.signups.onboarding import complete_site_setup as complete

	return complete(team)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60, user_based=True)
@require_capability("billing:manage", SETUP_DENIED)
def invite_members(rows: list | str, team: str | None = None) -> dict:
	"""Invite members to the team's site with their modules and role. The site emails them."""
	from central.signups.onboarding import invite_members as invite

	return invite(team, rows)


@frappe.whitelist(methods=["POST"])
@require_capability("billing:manage", SETUP_DENIED)
def finish_team_step(team: str | None = None) -> dict:
	"""Leave step 3, with or without invitations."""
	from central.signups.onboarding import finish_team_step as finish

	return finish(team)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60, user_based=True)
@require_capability("billing:manage", SETUP_DENIED)
def apply_master_setup(config: dict | str, team: str | None = None) -> dict:
	"""Send the CRM and Estimation defaults to the team's site and finish onboarding."""
	from central.signups.onboarding import apply_master_setup as apply

	return apply(team, config)
