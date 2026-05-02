from src.tasks import digest, community, owner

ALLOWED_TASK_TYPES = {"digest_mini", "digest_full", "digest_comment", "owner_command"}

def get_handler(task_type):
    if task_type == "digest_mini": return lambda t, c, m: digest.run(c, m, "digest_mini")
    if task_type == "digest_full": return lambda t, c, m: digest.run(c, m, "digest_full")
    if task_type == "digest_comment": return lambda t, c, m: community.process(c, m, t)
    if task_type == "owner_command": return lambda t, c, m: owner.process(c, m, t)
    return None
