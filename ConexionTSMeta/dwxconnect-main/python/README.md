# DWX_Connect - A simple multi-language MT4 connector

DWX_Connect provides functions to subscribe to tick and bar data, as well as to trade on MT4 or MT5 via python, java and C#. 
Its simple file-based communication also provides an easy starting point for implementations in other programming languages. 

## Configuration

Default MetaTrader paths and workspace mappings are now defined in `config.json`.
Multiple accounts can be specified under the `accounts` section and selected via
the `default_account` field or by passing the environment variable
`TS_ACCOUNT` when starting a connector.
