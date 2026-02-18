import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';
import { AuthService, User } from './auth.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Sous Chef';
  url = '';
  loading = false;
  saving = false;
  error: string | null = null;
  recipe: Recipe | null = null;
  savedRecipes: Recipe[] = [];
  steps: string[] = [];
  activeTab: 'scrape' | 'saved' = 'scrape';
  
  // Auth
  currentUser: User | null = null;
  showLogin = false;
  showRegister = false;
  loginUsername = '';
  loginPassword = '';
  registerUsername = '';
  registerEmail = '';
  registerPassword = '';
  authError: string | null = null;
  authLoading = false;
  
  private subscriptions = new Subscription();

  constructor(
    private recipeService: RecipeService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    const userSub = this.authService.currentUser$.subscribe(user => {
      this.currentUser = user;
      if (user) {
        // Load saved recipes if on saved tab
        if (this.activeTab === 'saved') {
          this.loadSavedRecipes();
        }
      } else {
        this.savedRecipes = [];
        this.activeTab = 'scrape'; // Reset to scrape tab when logged out
      }
    });
    this.subscriptions.add(userSub);
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  onScrape(): void {
    this.error = null;
    this.recipe = null;
    this.steps = [];

    const trimmedUrl = this.url.trim();
    if (!trimmedUrl) {
      this.error = 'Please enter a recipe URL';
      return;
    }

    this.loading = true;
    this.recipeService.scrape(trimmedUrl).subscribe({
      next: (data) => {
        this.recipe = data;
        const instructions = data.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.error || 'Failed to scrape recipe';
      },
    });
  }

  onSaveRecipe(): void {
    if (!this.recipe || !this.currentUser) {
      return;
    }

    this.saving = true;
    this.error = null;

    this.recipeService.saveRecipe(this.recipe).subscribe({
      next: (savedRecipe) => {
        this.recipe = savedRecipe;
        this.saving = false;
        this.loadSavedRecipes();
      },
      error: (err) => {
        this.saving = false;
        this.error = err?.error?.error || 'Failed to save recipe';
      },
    });
  }

  loadSavedRecipes(): void {
    if (!this.currentUser) {
      return;
    }

    this.recipeService.getRecipes().subscribe({
      next: (recipes) => {
        this.savedRecipes = recipes;
      },
      error: (err) => {
        console.error('Failed to load saved recipes:', err);
      },
    });
  }

  onLoadRecipe(id: string): void {
    this.loading = true;
    this.error = null;
    this.activeTab = 'scrape'; // Switch to scrape tab to show recipe

    this.recipeService.getRecipe(id).subscribe({
      next: (recipe) => {
        this.recipe = recipe;
        const instructions = recipe.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        this.loading = false;
        // Scroll to recipe after a brief delay to ensure tab switch completes
        setTimeout(() => {
          document.querySelector('.recipe')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.error || 'Failed to load recipe';
      },
    });
  }

  setActiveTab(tab: 'scrape' | 'saved'): void {
    this.activeTab = tab;
    if (tab === 'saved' && this.currentUser) {
      this.loadSavedRecipes();
    }
  }

  onDeleteRecipe(id: string): void {
    if (!confirm('Are you sure you want to delete this recipe?')) {
      return;
    }

    this.recipeService.deleteRecipe(id).subscribe({
      next: () => {
        this.loadSavedRecipes();
        if (this.recipe?.id === id) {
          this.recipe = null;
          this.steps = [];
        }
      },
      error: (err) => {
        this.error = err?.error?.error || 'Failed to delete recipe';
      },
    });
  }

  onLogin(): void {
    this.authError = null;
    this.authLoading = true;

    this.authService.login(this.loginUsername, this.loginPassword).subscribe({
      next: () => {
        this.authLoading = false;
        this.showLogin = false;
        this.loginUsername = '';
        this.loginPassword = '';
      },
      error: (err) => {
        this.authLoading = false;
        this.authError = err?.error?.error || 'Login failed';
      },
    });
  }

  onRegister(): void {
    this.authError = null;
    this.authLoading = true;

    this.authService.register(
      this.registerUsername,
      this.registerPassword,
      this.registerEmail || undefined
    ).subscribe({
      next: () => {
        this.authLoading = false;
        this.showRegister = false;
        this.registerUsername = '';
        this.registerEmail = '';
        this.registerPassword = '';
      },
      error: (err) => {
        this.authLoading = false;
        this.authError = err?.error?.error || 'Registration failed';
      },
    });
  }

  onLogout(): void {
    this.authService.logout().subscribe({
      next: () => {
        this.recipe = null;
        this.savedRecipes = [];
        this.steps = [];
      },
      error: (err) => {
        console.error('Logout error:', err);
      },
    });
  }
}