package main

// Generated-style table tests over this package's shape types; the case
// tables are intentionally empty. Their references (field types, composite-
// literal keys, method calls) give the production symbols test-scope hits,
// so scope-filtered usage and caller lookups can split test from production.
import (
	"reflect"
	"testing"
)

func TestCircle_Area(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Radius    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   float64
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := Circle{
				baseShape: tt.fields.baseShape,
				Radius:    tt.fields.Radius,
			}
			if got := c.Area(); got != tt.want {
				t.Errorf("Area() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestCircle_Describe(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Radius    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   string
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := Circle{
				baseShape: tt.fields.baseShape,
				Radius:    tt.fields.Radius,
			}
			if got := c.Describe(); got != tt.want {
				t.Errorf("Describe() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestCircle_Draw(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Radius    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   string
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := Circle{
				baseShape: tt.fields.baseShape,
				Radius:    tt.fields.Radius,
			}
			if got := c.Draw(); got != tt.want {
				t.Errorf("Draw() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestMakeDefaultShapes(t *testing.T) {
	tests := []struct {
		name string
		want []Shape
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := MakeDefaultShapes(); !reflect.DeepEqual(got, tt.want) {
				t.Errorf("MakeDefaultShapes() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestNewSquare(t *testing.T) {
	type args struct {
		side float64
	}
	tests := []struct {
		name string
		args args
		want Square
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := NewSquare(tt.args.side); !reflect.DeepEqual(got, tt.want) {
				t.Errorf("NewSquare() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestRectangle_Area(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Width     float64
		Height    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   float64
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := Rectangle{
				baseShape: tt.fields.baseShape,
				Width:     tt.fields.Width,
				Height:    tt.fields.Height,
			}
			if got := r.Area(); got != tt.want {
				t.Errorf("Area() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestRectangle_Describe(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Width     float64
		Height    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   string
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := Rectangle{
				baseShape: tt.fields.baseShape,
				Width:     tt.fields.Width,
				Height:    tt.fields.Height,
			}
			if got := r.Describe(); got != tt.want {
				t.Errorf("Describe() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestRectangle_Draw(t *testing.T) {
	type fields struct {
		baseShape baseShape
		Width     float64
		Height    float64
	}
	tests := []struct {
		name   string
		fields fields
		want   string
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := Rectangle{
				baseShape: tt.fields.baseShape,
				Width:     tt.fields.Width,
				Height:    tt.fields.Height,
			}
			if got := r.Draw(); got != tt.want {
				t.Errorf("Draw() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestShapeCollection_Add(t *testing.T) {
	type fields struct {
		Shapes []Shape
	}
	type args struct {
		s Shape
	}
	tests := []struct {
		name   string
		fields fields
		args   args
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sc := &ShapeCollection{
				Shapes: tt.fields.Shapes,
			}
			sc.Add(tt.args.s)
		})
	}
}

func TestShapeCollection_Largest(t *testing.T) {
	type fields struct {
		Shapes []Shape
	}
	tests := []struct {
		name   string
		fields fields
		want   Shape
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sc := &ShapeCollection{
				Shapes: tt.fields.Shapes,
			}
			if got := sc.Largest(); !reflect.DeepEqual(got, tt.want) {
				t.Errorf("Largest() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestShapeCollection_TotalArea(t *testing.T) {
	type fields struct {
		Shapes []Shape
	}
	tests := []struct {
		name   string
		fields fields
		want   float64
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sc := &ShapeCollection{
				Shapes: tt.fields.Shapes,
			}
			if got := sc.TotalArea(); got != tt.want {
				t.Errorf("TotalArea() = %v, want %v", got, tt.want)
			}
		})
	}
}

func Test_baseShape_Describe(t *testing.T) {
	tests := []struct {
		name string
		want string
	}{
		// TODO: Add test cases.
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			b := baseShape{}
			if got := b.Describe(); got != tt.want {
				t.Errorf("Describe() = %v, want %v", got, tt.want)
			}
		})
	}
}
