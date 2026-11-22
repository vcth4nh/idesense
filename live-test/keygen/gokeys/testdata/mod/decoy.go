package mod

type Dog struct{}

func (Dog) Speak() string { return "woof" }

type Robot struct{}

func (Robot) Speak() string { return "beep" }

func talk() string {
	d := Dog{}.Speak()
	r := Robot{}.Speak()
	return d + r
}
