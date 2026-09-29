class ProjectLoadError(RuntimeError):
    pass


def flatten_exception(exception) -> str:
    lines = [str(exception)]
    try:
        java_value = getattr(exception, "__javavalue__", None)
        if java_value:
            lines.append(str(java_value))
    except Exception:
        pass
    return "\n".join(line for line in lines if line)
