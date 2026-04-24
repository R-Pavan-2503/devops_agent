package model

import (
	"time"
)

type User struct {
	ID        string
	Username  string
	Status    string
	Password  string
	CreatedAt time.Time
}