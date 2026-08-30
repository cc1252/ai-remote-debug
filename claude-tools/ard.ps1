$Script = Join-Path $PSScriptRoot "ard.py"
py $Script @args
exit $LASTEXITCODE
