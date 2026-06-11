package sample

func Add(a int, b int) int {
	return a + b
}

type Store struct {
	size int
}

func (s *Store) Len() int {
	return s.size
}
