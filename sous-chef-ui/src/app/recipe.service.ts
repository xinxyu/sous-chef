import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Recipe {
  title: string | null;
  total_time: number | null;
  yields: string | null;
  ingredients: string[];
  instructions: string[] | string;
  image: string | null;
  host: string | null;
  nutrients: any;
}

@Injectable({
  providedIn: 'root',
})
export class RecipeService {
  // Flask API is running on port 4100
  private readonly apiUrl = 'http://localhost:4100/scrape';

  constructor(private http: HttpClient) {}

  scrape(url: string): Observable<Recipe> {
    return this.http.post<Recipe>(this.apiUrl, { url });
  }
}


