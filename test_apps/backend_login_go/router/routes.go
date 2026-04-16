package router

import (
	"net/http"
	"backend_login_go/api"
	"backend_login_go/service"
)

type Route struct {
	Path    string
	Handler http.HandlerFunc
}

func RegisterRoutes(authService service.AuthService) *http.ServeMux {
	mux := http.NewServeMux()
	routes := []Route{
		{Path: "/api/login", Handler: api.LoginEndpoint(authService)},
		{Path: "/api/profile", Handler: api.ProfileEndpoint},
	}

	for _, route := range routes {
		mux.HandleFunc(route.Path, route.Handler)
	}

	return mux
}