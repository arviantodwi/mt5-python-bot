from unittest.mock import MagicMock, patch

import pytest

from app.bot import clear_terminal, healthcheck, init_mt5, run, shutdown_mt5


def test_healthcheck():
    """Tests the healthcheck function."""
    assert healthcheck() == "Bot is healthy!"


@patch("os.system")
def test_clear_terminal_windows(mock_system):
    """Tests clear_terminal on Windows."""
    with patch("os.name", "nt"):
        clear_terminal()
        mock_system.assert_called_once_with("cls")


@patch("os.system")
def test_clear_terminal_unix(mock_system):
    """Tests clear_terminal on Unix/Linux."""
    with patch("os.name", "posix"):
        clear_terminal()
        mock_system.assert_called_once_with("clear")


@patch("app.bot.mt5")
@patch("app.bot.print")
def test_init_mt5_success(mock_print, mock_mt5):
    """Tests successful MT5 initialization."""
    # Arrange
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = MagicMock(name="Test Terminal")
    mock_mt5.version.return_value = (5, 0, 1234)
    mock_mt5.symbol_select.return_value = True
    mock_mt5.account_info.return_value = MagicMock(login="testuser", server="testserver")

    with patch("app.bot.SYMBOL", "EURUSD"):
        # Act
        init_mt5()

    # Assert
    mock_mt5.initialize.assert_called_once()
    mock_mt5.terminal_info.assert_called_once()
    mock_mt5.symbol_select.assert_called_once_with("EURUSD", True)
    mock_mt5.account_info.assert_called_once()
    assert mock_print.call_count == 4


@patch("app.bot.mt5")
def test_init_mt5_initialization_fails(mock_mt5):
    """Tests MT5 initialization failure."""
    mock_mt5.initialize.return_value = False
    mock_mt5.last_error.return_value = "Connection failed"

    with pytest.raises(RuntimeError, match="MT5 initialization failed. Reason: Connection failed."):
        init_mt5()


@patch("app.bot.mt5")
def test_init_mt5_terminal_info_fails(mock_mt5):
    """Tests failure to retrieve terminal info."""
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = None
    mock_mt5.last_error.return_value = "Terminal info error"

    with pytest.raises(RuntimeError, match="Unable to retrieve MT5 terminal information. Reason: Terminal info error."):
        init_mt5()


@patch("app.bot.mt5")
def test_init_mt5_no_symbol(mock_mt5):
    """Tests runtime error if SYMBOL is not set."""
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = MagicMock(name="Test Terminal")
    with patch("app.bot.SYMBOL", ""):
        with pytest.raises(RuntimeError, match=r"Active trading symbol is not set \(env 'SYMBOL'\)."):
            init_mt5()


@patch("app.bot.mt5")
def test_init_mt5_symbol_select_fails(mock_mt5):
    """Tests failure to select a symbol."""
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = MagicMock(name="Test Terminal")
    mock_mt5.symbol_select.return_value = False
    mock_mt5.last_error.return_value = "Invalid symbol"

    with patch("app.bot.SYMBOL", "INVALID"):
        with pytest.raises(RuntimeError, match="Failed to select symbol 'INVALID'. Reason: Invalid symbol."):
            init_mt5()


@patch("app.bot.mt5")
def test_init_mt5_account_info_fails(mock_mt5):
    """Tests failure to retrieve account info."""
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = MagicMock(name="Test Terminal")
    mock_mt5.symbol_select.return_value = True
    mock_mt5.account_info.return_value = None
    mock_mt5.last_error.return_value = "Account info error"

    with patch("app.bot.SYMBOL", "EURUSD"):
        with pytest.raises(
            RuntimeError, match=r"\[Error\] Unable to fetch account information. Reason: Account info error."
        ):
            init_mt5()


@patch("app.bot.mt5")
@patch("app.bot.print")
def test_shutdown_mt5_success(mock_print, mock_mt5):
    """Tests successful MT5 shutdown."""
    shutdown_mt5()
    mock_mt5.shutdown.assert_called_once()
    mock_print.assert_called_once_with("Shutting down...")


@patch("app.bot.mt5")
@patch("app.bot.print")
def test_shutdown_mt5_handles_exception(mock_print, mock_mt5):
    """Tests that shutdown_mt5 handles exceptions from mt5.shutdown()."""
    mock_mt5.shutdown.side_effect = Exception("Shutdown error")
    try:
        shutdown_mt5()
    except Exception:
        pytest.fail("shutdown_mt5() raised an exception unexpectedly!")

    mock_mt5.shutdown.assert_called_once()
    mock_print.assert_called_once_with("Shutting down...")


@patch("app.bot.clear_terminal")
@patch("app.bot.healthcheck")
@patch("app.bot.init_mt5")
@patch("app.bot.shutdown_mt5")
@patch("app.bot.mt5")
@patch("app.bot.time.sleep", side_effect=[None, KeyboardInterrupt])
@patch("app.bot.print")
@patch("app.bot.datetime")
def test_run_happy_path(
    mock_datetime,
    mock_print,
    mock_sleep,
    mock_mt5,
    mock_shutdown,
    mock_init,
    mock_healthcheck,
    mock_clear,
):
    """Tests the main run function ensuring all setup and teardown functions are called."""
    # Arrange
    mock_tick = MagicMock()
    mock_tick.bid = 1.2345
    mock_tick.ask = 1.235
    mock_mt5.symbol_info_tick.return_value = mock_tick
    mock_now = MagicMock()
    mock_now.strftime.return_value = "12:34:56"
    mock_datetime.now.return_value = mock_now
    # mock_healthcheck.return_value = "Bot is healthy!"

    with patch("app.bot.SYMBOL", "EURUSD"):
        # Act
        run()

    # Assert
    mock_clear.assert_called_once()
    mock_healthcheck.assert_called_once()
    mock_init.assert_called_once()
    mock_mt5.symbol_info_tick.assert_any_call("EURUSD")

    # Check print calls
    # mock_print.assert_any_call("Bot is healthy!")
    mock_print.assert_any_call("Start EURUSD rate polling.")

    # Check for the tick print specifically
    found_tick_print = False
    for call in mock_print.call_args_list:
        args, kwargs = call
        if args and "Bid=" in args[0] and "Ask=" in args[0]:
            found_tick_print = True
            assert "12:34:56" in args[0]
            assert "Bid=1.2345" in args[0]
            assert "Ask=1.235" in args[0]
            assert kwargs == {"end": "\r", "flush": True}
            break
    assert found_tick_print, "Tick print call not found"

    mock_print.assert_any_call("", end="\n")

    assert mock_sleep.call_count == 2
    mock_shutdown.assert_called_once()
