# -*- coding: utf-8 -*-

import inspect
import types
import typing
import unittest.mock

import invoke


def fix_annotations() -> None:
    """
    Copied from https://github.com/pyinvoke/invoke/issues/357#issuecomment-583851322.
    """

    def patched_inspect_getargspec(function: types.FunctionType) -> inspect.ArgSpec:
        spec = inspect.getfullargspec(function)

        return inspect.ArgSpec(
            args=spec.args,
            varargs=spec.varargs,
            keywords=spec.varkw,
            defaults=spec.defaults or ()
        )

    original_task_argspec = invoke.tasks.Task.argspec

    def patched_task_argspec(*args: typing.Any, **kwargs: typing.Any) -> None:
        with unittest.mock.patch(target="inspect.getargspec", new=patched_inspect_getargspec):
            return original_task_argspec(*args, **kwargs)

    invoke.tasks.Task.argspec = patched_task_argspec
