package controller

// Error is a structured error returned by the auth controller.
// It carries both a human-readable message and an HTTP status code so the
// API layer can propagate both without extra wrapping.
type Error struct {
	Msg  string
	Code int
}

// NewError constructs a controller.Error.
func NewError(msg string, code int) *Error {
	return &Error{Msg: msg, Code: code}
}

// Error implements the standard error interface.
func (e *Error) Error() string {
	return e.Msg
}