package controller

import (
	"errors"
	"net/http"
)

type Error struct {
	Msg  string
	Code int
}

func NewError(msg string, code int) *Error {
	return &Error{Msg: msg, Code: code}
}

func (e *Error) Error() string {
	return e.Msg
}