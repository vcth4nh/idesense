package mod

import "sort"

type Lener interface {
	Len() int
}

// ByAge implements sort.Interface; Queue implements only Lener.
type ByAge []int

func (a ByAge) Len() int { return len(a) }

func (a ByAge) Less(i, j int) bool { return a[i] < a[j] }

func (a ByAge) Swap(i, j int) { a[i], a[j] = a[j], a[i] }

type Queue struct{}

func (Queue) Len() int { return 0 }

func sizes(l Lener) int {
	sort.Sort(ByAge(nil))
	return l.Len()
}
