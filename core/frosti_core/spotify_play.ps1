# Presses Play on a song in the Spotify desktop app's search page (no Premium API: the app is driven like a user would).
# Usage: spotify_play.ps1 "<title> <artist>"  (the search must already be open). Exit 0 = pressed, 1 = not found in time.
param([Parameter(Mandatory)][string]$Query)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$Desc = [System.Windows.Automation.TreeScope]::Descendants
$q = $Query.ToLower()
$want = 'search for ' + ($q -replace ' ', '+')  # the page title Spotify gives this search
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 400
    $p = Get-Process Spotify -ErrorAction SilentlyContinue | Where-Object MainWindowTitle | Select-Object -First 1
    if (-not $p) { continue }
    $w = $A::FromHandle($p.MainWindowHandle)
    # a song row is a title link, then artist links, with a Play button just before ("Play <title>") or after ("Play").
    # The query is "<title> <first artist>": the row must match the title (either may extend the other: Spotify adds
    # '(from "Film")'); a matching artist counts most, because covers share titles.
    $Link = [System.Windows.Automation.ControlType]::Hyperlink; $Btn = [System.Windows.Automation.ControlType]::Button
    $all = $w.FindAll($Desc, [System.Windows.Automation.Condition]::TrueCondition)
    # read once; elements vanish while the page redraws, so a failed read is just an empty slot
    $names = @(foreach ($e in $all) { try { ([string]$e.Current.Name).ToLower() } catch { '' } })
    $types = @(foreach ($e in $all) { try { $e.Current.ControlType } catch { $null } })
    if (-not ($names | Where-Object { $_.StartsWith($want) }) -and $i -lt 10) { continue }  # wait for this search's page, not the last one
    $best = $null; $score = 0
    for ($k = 0; $k -lt $all.Count; $k++) {
        $t = $names[$k]
        if ($types[$k] -ne $Link -or $t.Length -lt 2) { continue }
        $play = $null
        for ($m = [Math]::Max(0, $k - 5); $m -lt [Math]::Min($k + 15, $all.Count); $m++) {  # the top-result card puts Play after all its artists
            if ($types[$m] -eq $Btn -and ($names[$m] -eq 'play' -or $names[$m] -eq "play $t")) { $play = $all[$m]; break }
        }
        if (-not $play) { continue }
        $s = 0; $qt = $q
        for ($m = $k + 1; $m -lt [Math]::Min($k + 6, $all.Count); $m++) {
            $artist = $names[$m]  # not $a: PowerShell names ignore case, and $a would overwrite $A above
            if ($types[$m] -eq $Link -and $artist -and $q.EndsWith(" $artist")) { $s = 1000; $qt = $q.Substring(0, $q.Length - $artist.Length - 1); break }
        }
        # a shorter Spotify title ("Neeye" for "Neeye Punchiri - One Side Love") counts only with the artist or most of the name
        $short = $qt.StartsWith($t) -and ($s -ge 1000 -or $t.Length * 2 -ge $qt.Length)
        if ($t -eq $qt) { $s += 600 } elseif ($t.StartsWith($qt) -or $short) { $s += 500 + [Math]::Min($t.Length, $qt.Length) } else { continue }
        if ($s -gt $score) { $best = $play; $score = $s; $title = @($t, $qt)[[int]($qt.Length -lt $t.Length)] }  # the shorter: what the window title surely contains
    }
    if ($best) {
        $before = $p.MainWindowTitle
        try { $best.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } catch { continue }
        # a press while the page is still drawing is lost: done only once the window title changes to "<artist> - <title>"
        for ($j = 0; $j -lt 8; $j++) {
            Start-Sleep -Milliseconds 400
            $now = (Get-Process -Id $p.Id -ErrorAction SilentlyContinue).MainWindowTitle
            if ($now -and $now -ne $before -and $now.ToLower().Contains(" - $title")) { exit 0 }
        }
    }
}
exit 1
