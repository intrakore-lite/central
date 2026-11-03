from central.central.doctype.central_settings.central_settings import enable_invite_only


def execute() -> None:
	"""Make Intrakore Cloud invite-only, the field's default, with 7-day activation links."""
	enable_invite_only()
