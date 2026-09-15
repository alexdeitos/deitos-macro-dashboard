# Verificação rápida do RTDTrading.RTDServer
Write-Host "=== RTDTrading.RTDServer / Profit ===" -ForegroundColor Cyan

try {
    $t = [System.Type]::GetTypeFromProgID("RTDTrading.RTDServer")
    if ($null -eq $t) {
        Write-Host "ERRO: RTDTrading.RTDServer não está registrado no Windows." -ForegroundColor Red
        Write-Host "Abra o Profit, use a exportação RTD/DDE e depois verifique novamente."
    } else {
        Write-Host "OK: ProgID registrado -> $($t.FullName)" -ForegroundColor Green
    }
} catch {
    Write-Host "Falha consultando ProgID: $($_.Exception.Message)" -ForegroundColor Red
}

$paths = @(
  "HKCU:\Software\Classes\RTDTrading.RTDServer",
  "HKLM:\Software\Classes\RTDTrading.RTDServer",
  "HKLM:\Software\Classes\WOW6432Node\CLSID"
)

Write-Host "`nRegistros encontrados:" -ForegroundColor Yellow
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Host "  $p" -ForegroundColor Green }
}

Write-Host @"
`nNo Excel:
1) Arquivo > Opções > Suplementos.
2) Gerenciar = Itens Desabilitados > Ir... -> reative rtdtrading.rtdserver se estiver lá.
3) Gerenciar = Suplementos COM > Ir... -> confirme o suplemento do Profit.
4) Guia Conteúdo Externo -> habilite todas as Conexões de Dados e atualização automática de links.
5) Com o Profit aberto, faça novamente a exportação RTD/DDE.
"@
