Output queue-simple.gif

Set Shell "bash"
Set FontSize 22
Set Width 1400
Set Height 800
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set FontFamily "Menlo"
Set Framerate 30

Sleep 500ms

Type "echo 'auth module' > auth.py"
Enter
Sleep 600ms

Type `gitfc queue "add user authentication"`
Enter
Sleep 1500ms

Type "echo 'validation module' > validate.py"
Enter
Sleep 600ms

Type `gitfc queue "add input validation"`
Enter
Sleep 1500ms

Type "echo 'error handling' > errors.py"
Enter
Sleep 600ms

Type `gitfc queue "add error handling"`
Enter
Sleep 1500ms

Type "gitfc queue list"
Enter
Sleep 2000ms

Type "gitfc queue status"
Enter
Sleep 2500ms
