// Package interfaces defines shared interface contracts used across
// controller, service, and utils packages to prevent circular imports.
package interfaces

// PasswordHasherInterface abstracts password hashing so that the service
// layer does not need to depend on the concrete utils implementation.
type PasswordHasherInterface interface {
	HashPassword(password string) (string, error)
	CompareHashAndPassword(hashedPassword string, password string) error
}

// ErrorHandlerInterface abstracts error construction so the controller
// can be injected with a test double without a real database.
type ErrorHandlerInterface interface {
	HandleError(message string, code int) error
}
