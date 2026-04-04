Output hero.gif

Set Shell "bash"
Set FontSize 22
Set Width 1400
Set Height 600
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set FontFamily "Menlo"
Set Framerate 30

Sleep 500ms

Type "echo 'welcome to my site' > index.html"
Enter
Sleep 800ms

Type `gitfc -a -v "add homepage" "-2d"`
Enter
Sleep 2000ms

Type "git log --oneline --format='%h  %ad  %s' --date=short"
Enter
Sleep 2500ms
