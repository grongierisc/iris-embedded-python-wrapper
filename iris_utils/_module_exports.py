def copy_public_exports(module, module_globals, skip=(), *, include_getattr=False):
    skipped = set(skip)
    exported_names = getattr(module, "__all__", None)
    if exported_names is None:
        exported_names = [name for name in module.__dict__ if not name.startswith("_")]

    for name in exported_names:
        if name in skipped:
            continue
        module_globals[name] = getattr(module, name)

    if include_getattr and hasattr(module, "__getattr__"):
        module_globals["__getattr__"] = getattr(module, "__getattr__")
