using Microsoft.AspNetCore.Mvc;
using backend_login_cs.Models;
using backend_login_cs.Services;

namespace backend_login_cs.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class AuthController : ControllerBase
    {
        private readonly IAuthService _authService;

        public AuthController(IAuthService authService)
        {
            _authService = authService;
        }

        [HttpPost("login")]
        public IActionResult Login([FromBody] LoginRequest loginRequest)
        {
            if (_authService.Authenticate(loginRequest.Username, loginRequest.Password))
            {
                return Ok("Login successful");
            }
            return Unauthorized("Invalid username or password");
        }
    }
}