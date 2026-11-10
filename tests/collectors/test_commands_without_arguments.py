from __future__ import annotations

import contextlib
import io
import unittest

from barreiras_collectors.commands import (
    collect_bahia_special_transfers,
    collect_cgu_federal_amendments,
)


class CommandsWithoutArgumentsTests(unittest.TestCase):
    """`--help` e argumento desconhecido não podem disparar a coleta."""

    def test_help_and_unknown_argument_exit_before_collecting(self) -> None:
        commands = (collect_bahia_special_transfers, collect_cgu_federal_amendments)
        for command in commands:
            for arguments, code in ((["--help"], 0), (["--inexistente"], 2)):
                with (
                    self.subTest(command=command.__name__, arguments=arguments),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    command.main(arguments)
                self.assertEqual(raised.exception.code, code)


if __name__ == "__main__":
    unittest.main()
